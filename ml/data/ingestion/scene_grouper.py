"""Scene Grouping and Group-Aware Partitioning Utilities.

Prevents data leakage by clustering temporally correlated frames, video sequences,
and perceptual near-duplicates into atomic groups prior to split assignment.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Dict, List, Set, Tuple
from ml.data.ingestion.hasher import hamming_distance


@dataclass
class SceneGroup:
    """Represents an atomic cluster of correlated images that must not cross split boundaries."""
    group_id: str
    class_name: str
    source_id: str
    member_files: List[str] = field(default_factory=list)
    dhashes: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.member_files)


class SceneGrouper:
    """Clusters candidate images into atomic scene groups based on capture session and perceptual similarity."""

    def __init__(self, dhash_threshold: int = 3):
        """Initialize SceneGrouper.

        Args:
            dhash_threshold: Maximum Hamming distance for perceptual near-duplicate clustering.
        """
        self.dhash_threshold = dhash_threshold

    @staticmethod
    def extract_session_id(file_name: str, source_id: str) -> str:
        """Extract capture session or sequence prefix from filename.

        Examples:
        - 'AoF00123.jpg' -> 'AoF00' (blocks of 100 frames)
        - 'seq_02_frame_045.jpg' -> 'seq_02'
        - 'fire.123.png' -> 'fire.123'
        - 'HPWREN_rm-w-mobo-c_20190822_1234.jpg' -> camera+day prefix
        """
        stem = file_name.rsplit(".", 1)[0]

        # Check for sequence or video pattern: seq_XX or video_XX or cam_XX
        m_seq = re.search(r"(seq[_-]?\d+|video[_-]?\d+|cam[_-]?\d+)", stem, re.IGNORECASE)
        if m_seq:
            return f"{source_id}_{m_seq.group(1).lower()}"

        # HPWREN timestamp pattern: camera_YYYYMMDD_HHMM
        m_hpwren = re.match(r"^([a-zA-Z0-9_\-]+)_(\d{8})_\d+", stem)
        if m_hpwren:
            return f"{source_id}_{m_hpwren.group(1)}_{m_hpwren.group(2)}"

        # Surveillance camera burst pattern: AoFXXXXX (group into tight 10-frame bursts)
        m_aof = re.match(r"^(AoF)(\d+)$", stem, re.IGNORECASE)
        if m_aof:
            bucket = int(m_aof.group(2)) // 10
            return f"{source_id}_aof_{bucket}"

        # Default for still images: each still image is an atomic capture session
        # Perceptual dHash near-duplicate clustering will link any visually identical frames
        return f"{source_id}_{stem}"

    def cluster_images(
        self,
        image_records: List[Dict[str, str]],
    ) -> List[SceneGroup]:
        """Cluster a list of image records into SceneGroups.

        Each record is a dict with keys:
        - 'file_path': str
        - 'file_name': str
        - 'class_name': str
        - 'source_id': str
        - 'dhash': str (16-char hex)

        Returns:
            List of disjoint SceneGroup objects.
        """
        # First group by (class_name, session_id)
        session_map: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
        for rec in image_records:
            cls = rec.get("class_name") or rec.get("target_class") or "unknown"
            src = rec.get("source_id", "unknown")
            file_name = rec.get("file_name", "unknown")
            sess = self.extract_session_id(file_name, src)
            key = (cls, sess)
            if key not in session_map:
                session_map[key] = []
            session_map[key].append(rec)

        # Build initial groups from session map
        groups: List[SceneGroup] = []
        for (cls, sess), recs in session_map.items():
            first_src = recs[0].get("source_id", "unknown")
            grp = SceneGroup(
                group_id=f"grp_{cls}_{sess}",
                class_name=cls,
                source_id=first_src,
                member_files=[r["file_path"] for r in recs],
                dhashes=[r["dhash"] for r in recs if "dhash" in r],
            )
            groups.append(grp)

        # Merge groups within the same class if any member images have dHash distance <= threshold
        merged_groups = self._merge_perceptually_similar_groups(groups)
        return merged_groups

    def _merge_perceptually_similar_groups(self, groups: List[SceneGroup]) -> List[SceneGroup]:
        """Merge groups within the same class that share near-duplicate dHashes."""
        if not groups:
            return []

        n = len(groups)
        # Disjoint set / union-find
        parent = list(range(n))

        def find(i: int) -> int:
            if parent[i] == i:
                return i
            parent[i] = find(parent[i])
            return parent[i]

        def union(i: int, j: int) -> None:
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        # Precompute integer hashes for fast bitwise XOR
        group_hash_ints: List[List[int]] = [
            [int(h, 16) for h in g.dhashes if h] for g in groups
        ]

        # Group indices by class to only compare within the same class
        by_class: Dict[str, List[int]] = defaultdict(list)
        for idx, g in enumerate(groups):
            by_class[g.class_name].append(idx)

        threshold = self.dhash_threshold

        for cls_name, indices in by_class.items():
            num_in_class = len(indices)
            for i_pos in range(num_in_class):
                idx_i = indices[i_pos]
                hashes_i = group_hash_ints[idx_i]
                if not hashes_i:
                    continue

                for j_pos in range(i_pos + 1, num_in_class):
                    idx_j = indices[j_pos]
                    if find(idx_i) == find(idx_j):
                        continue

                    hashes_j = group_hash_ints[idx_j]
                    if not hashes_j:
                        continue

                    # Fast hamming check
                    is_close = False
                    for h1 in hashes_i:
                        for h2 in hashes_j:
                            if bin(h1 ^ h2).count("1") <= threshold:
                                is_close = True
                                break
                        if is_close:
                            break

                    if is_close:
                        union(idx_i, idx_j)

        # Collect merged groups
        clusters: Dict[int, List[SceneGroup]] = {}
        for idx in range(n):
            root = find(idx)
            if root not in clusters:
                clusters[root] = []
            clusters[root].append(groups[idx])

        result: List[SceneGroup] = []
        for root, grp_list in clusters.items():
            if len(grp_list) == 1:
                result.append(grp_list[0])
            else:
                combined_files: List[str] = []
                combined_hashes: List[str] = []
                for g in grp_list:
                    combined_files.extend(g.member_files)
                    combined_hashes.extend(g.dhashes)
                primary = grp_list[0]
                result.append(
                    SceneGroup(
                        group_id=f"{primary.group_id}_merged",
                        class_name=primary.class_name,
                        source_id=primary.source_id,
                        member_files=combined_files,
                        dhashes=combined_hashes,
                    )
                )

        return result
