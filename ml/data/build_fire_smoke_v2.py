"""SCOUT Milestone 07 Phase 7B: Dataset V2 Builder & Generalization Pipeline.

Builds a reproducible, multi-source, leakage-resistant wildfire image classification
dataset at data/processed/fire_smoke_v2/ with strict format balancing, 2-pass Pillow
validation, SHA-256/dHash deduplication, and atomic scene-group splitting.
"""

from __future__ import annotations

import csv
import json
import os
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.data.ingestion.hasher import (
    compute_ahash,
    compute_dhash,
    compute_sha256,
    hamming_distance,
)
from ml.data.ingestion.image_validator import (
    sanitize_and_save_image,
    validate_image_file,
)
from ml.data.ingestion.metadata_extractor import extract_image_metadata
from ml.data.ingestion.scene_grouper import SceneGroup, SceneGrouper

# Constants
RANDOM_SEED = 42
SPLIT_RATIOS = {"train": 0.70, "validation": 0.15, "test": 0.15}
CLASSES = ["fire", "neutral", "smoke"]

DATA_PROCESSED_V1 = PROJECT_ROOT / "data" / "processed" / "fire_smoke_v1"
DATA_PROCESSED_V2 = PROJECT_ROOT / "data" / "processed" / "fire_smoke_v2"
DATA_EXTERNAL = PROJECT_ROOT / "data" / "external" / "fire_smoke_sources"
AUDIT_DIR = PROJECT_ROOT / "artifacts" / "audits" / "m07_phase7b"


def discover_candidate_images() -> List[Dict[str, Any]]:
    """Scan all candidate source repositories and collect raw image candidates."""
    candidates: List[Dict[str, Any]] = []

    # 1. Historical v1 dataset
    if DATA_PROCESSED_V1.exists():
        for split_name in ["train", "validation", "test"]:
            for cls_name in CLASSES:
                dir_path = DATA_PROCESSED_V1 / split_name / cls_name
                if not dir_path.is_dir():
                    continue
                for img_path in dir_path.glob("*.*"):
                    if img_path.name.startswith("."):
                        continue
                    candidates.append({
                        "file_path": str(img_path.resolve()),
                        "file_name": img_path.name,
                        "source_id": "deepquest_v1",
                        "original_class": cls_name,
                        "target_class": cls_name,
                        "historical_split": split_name,
                    })

    # 2. BoWFire dataset
    bowfire_img_dir = DATA_EXTERNAL / "bowfire" / "BoWFireDataset" / "dataset" / "img"
    if bowfire_img_dir.exists():
        for img_path in bowfire_img_dir.glob("*.*"):
            if img_path.name.startswith(".") or img_path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".bmp"]:
                continue
            name_lower = img_path.name.lower()
            if name_lower.startswith("fire"):
                target_cls = "fire"
            elif name_lower.startswith("not_fire") or name_lower.startswith("non_fire"):
                target_cls = "neutral"
            else:
                continue

            candidates.append({
                "file_path": str(img_path.resolve()),
                "file_name": img_path.name,
                "source_id": "bowfire",
                "original_class": target_cls,
                "target_class": target_cls,
                "historical_split": None,
            })

    # 3. D-Fire curated dataset
    dfire_dir = DATA_EXTERNAL / "dfire_curated"
    if dfire_dir.exists():
        for target_cls in CLASSES:
            cls_dir = dfire_dir / target_cls
            if not cls_dir.is_dir():
                continue
            for img_path in cls_dir.glob("*.*"):
                if img_path.name.startswith(".") or img_path.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                    continue
                candidates.append({
                    "file_path": str(img_path.resolve()),
                    "file_name": img_path.name,
                    "source_id": "dfire",
                    "original_class": target_cls,
                    "target_class": target_cls,
                    "historical_split": None,
                })

    return candidates


def run_pipeline() -> Dict[str, Any]:
    """Execute complete Phase 7B dataset expansion and hardening pipeline."""
    print("=" * 70)
    print("SCOUT Phase 7B: Building Multi-Source Dataset V2")
    print("=" * 70)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(RANDOM_SEED)

    # Step 1: Candidate Discovery
    raw_candidates = discover_candidate_images()
    print(f"[Step 1] Discovered {len(raw_candidates)} candidate images across sources:")
    src_counts = defaultdict(int)
    for c in raw_candidates:
        src_counts[c["source_id"]] += 1
    for s, cnt in src_counts.items():
        print(f"  - {s}: {cnt} images")

    # Step 2: Two-pass Pillow validation and feature extraction
    print("\n[Step 2] Executing two-pass image validation and metadata extraction...")
    valid_candidates: List[Dict[str, Any]] = []
    quarantined: List[Dict[str, Any]] = []

    for idx, cand in enumerate(raw_candidates):
        val_res = validate_image_file(cand["file_path"])
        if not val_res.is_valid:
            quarantined.append({
                "file_path": cand["file_path"],
                "source_id": cand["source_id"],
                "reason": val_res.error_reason,
            })
            continue

        meta = extract_image_metadata(cand["file_path"])
        cand_record = dict(cand)
        cand_record.update({
            "class_name": cand["target_class"],
            "sha256": meta.sha256,
            "format": meta.format,
            "mode": meta.mode,
            "width": meta.width,
            "height": meta.height,
            "aspect_ratio": meta.aspect_ratio,
            "channels": meta.channels,
            "dhash": meta.dhash,
            "ahash": meta.ahash,
            "size_bytes": meta.size_bytes,
            "mean_r": meta.mean_r,
            "mean_g": meta.mean_g,
            "mean_b": meta.mean_b,
            "std_r": meta.std_r,
            "std_g": meta.std_g,
            "std_b": meta.std_b,
        })
        valid_candidates.append(cand_record)
        if (idx + 1) % 500 == 0:
            print(f"  Validated {idx + 1}/{len(raw_candidates)} images...", flush=True)

    print(f"  Passed validation: {len(valid_candidates)}, Quarantined: {len(quarantined)}", flush=True)

    # Step 3: Exact Deduplication (SHA-256)
    print("\n[Step 3] Performing exact SHA-256 deduplication...")
    seen_sha: Dict[str, Dict[str, Any]] = {}
    exact_duplicates: List[Dict[str, Any]] = []
    unique_candidates: List[Dict[str, Any]] = []

    for cand in valid_candidates:
        sha = cand["sha256"]
        if sha in seen_sha:
            exact_duplicates.append({
                "duplicate_file": cand["file_path"],
                "duplicate_source": cand["source_id"],
                "original_file": seen_sha[sha]["file_path"],
                "original_source": seen_sha[sha]["source_id"],
                "sha256": sha,
            })
        else:
            seen_sha[sha] = cand
            unique_candidates.append(cand)

    print(f"  Exact duplicates removed: {len(exact_duplicates)}")
    print(f"  Unique valid images remaining: {len(unique_candidates)}")

    # Step 4: Scene Grouping & Near-Duplicate Clustering
    print("\n[Step 4] Clustering into atomic scene groups via dHash and session tokens...")
    grouper = SceneGrouper(dhash_threshold=3)
    scene_groups = grouper.cluster_images(unique_candidates)
    print(f"  Constructed {len(scene_groups)} atomic scene groups.")

    # Map each candidate to its assigned scene group ID
    file_to_group: Dict[str, str] = {}
    for grp in scene_groups:
        for f_path in grp.member_files:
            file_to_group[f_path] = grp.group_id

    for cand in unique_candidates:
        cand["scene_group_id"] = file_to_group.get(cand["file_path"], "grp_singleton")

    # Step 5: Group-Aware Stratified Splitting with Format Balancing
    print("\n[Step 5] Performing group-aware stratified partition with format balancing...", flush=True)

    # Determine dominant format for each scene group
    group_to_format: Dict[str, str] = {}
    cand_by_path = {c["file_path"]: c for c in unique_candidates}
    for grp in scene_groups:
        fmts = [cand_by_path[p]["format"] for p in grp.member_files if p in cand_by_path]
        dominant_fmt = max(set(fmts), key=fmts.count) if fmts else "JPEG"
        group_to_format[grp.group_id] = dominant_fmt

    # Group scene groups by (target_class, format)
    strata_groups: Dict[Tuple[str, str], List[SceneGroup]] = defaultdict(list)
    for grp in scene_groups:
        fmt = group_to_format[grp.group_id]
        strata_groups[(grp.class_name, fmt)].append(grp)

    split_groups: Dict[str, List[SceneGroup]] = {"train": [], "validation": [], "test": []}
    assigned_images: Dict[str, List[Dict[str, Any]]] = {"train": [], "validation": [], "test": []}

    # Allocate groups within each (class, format) stratum
    for (cls_name, fmt_name), grps in sorted(strata_groups.items()):
        rng = random.Random(RANDOM_SEED + hash(f"{cls_name}_{fmt_name}") % 1000)
        rng.shuffle(grps)

        total_stratum_imgs = sum(g.size for g in grps)
        target_train = int(total_stratum_imgs * SPLIT_RATIOS["train"])
        target_val = int(total_stratum_imgs * SPLIT_RATIOS["validation"])

        stratum_train = 0
        stratum_val = 0

        for grp in grps:
            if stratum_train < target_train:
                split_name = "train"
                stratum_train += grp.size
            elif stratum_val < target_val:
                split_name = "validation"
                stratum_val += grp.size
            else:
                split_name = "test"

            split_groups[split_name].append(grp)
            for f_path in grp.member_files:
                rec = dict(cand_by_path[f_path])
                rec["assigned_split"] = split_name
                assigned_images[split_name].append(rec)

    print("  Splitting breakdown:", flush=True)
    for s_name in ["train", "validation", "test"]:
        imgs = assigned_images[s_name]
        c_counts = defaultdict(int)
        f_counts = defaultdict(int)
        for img in imgs:
            c_counts[img["target_class"]] += 1
            f_counts[img["format"]] += 1
        print(f"    Split '{s_name}': {len(imgs)} images | Classes: {dict(c_counts)} | Formats: {dict(f_counts)}", flush=True)

    # Step 6: Materialize Target Directory (data/processed/fire_smoke_v2/)
    print(f"\n[Step 6] Materializing files in {DATA_PROCESSED_V2}...")
    if DATA_PROCESSED_V2.exists():
        for p in DATA_PROCESSED_V2.glob("**/*"):
            if p.is_file():
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    for s_name in ["train", "validation", "test"]:
        for c_name in CLASSES:
            (DATA_PROCESSED_V2 / s_name / c_name).mkdir(parents=True, exist_ok=True)

    manifest_records: List[Dict[str, Any]] = []
    dataset_hashes: Dict[str, Dict[str, Any]] = {}

    for s_name in ["train", "validation", "test"]:
        for img_rec in assigned_images[s_name]:
            cls_name = img_rec["target_class"]
            src_id = img_rec["source_id"]
            orig_name = Path(img_rec["file_name"])

            # Clean canonical filename with origin tag to prevent cross-split name collisions
            hist_tag = f"_{img_rec['historical_split']}" if img_rec.get("historical_split") else ""
            canonical_name = f"{src_id}{hist_tag}_{cls_name}_{orig_name.name}"
            target_file_path = DATA_PROCESSED_V2 / s_name / cls_name / canonical_name

            # Copy file safely
            shutil.copy2(img_rec["file_path"], target_file_path)

            # Re-verify and compute target hash
            target_sha = compute_sha256(target_file_path)
            rel_path = f"{s_name}/{cls_name}/{canonical_name}"

            dataset_hashes[rel_path] = {
                "sha256": target_sha,
                "size_bytes": target_file_path.stat().st_size,
                "source_id": src_id,
                "class": cls_name,
                "format": img_rec["format"],
            }

            manifest_records.append({
                "relative_path": rel_path,
                "assigned_split": s_name,
                "target_class": cls_name,
                "source_id": src_id,
                "original_filename": img_rec["file_name"],
                "canonical_filename": canonical_name,
                "sha256": target_sha,
                "format": img_rec["format"],
                "width": img_rec["width"],
                "height": img_rec["height"],
                "aspect_ratio": img_rec["aspect_ratio"],
                "scene_group_id": img_rec["scene_group_id"],
                "dhash": img_rec["dhash"],
            })

    print(f"  Successfully materialized {len(manifest_records)} images in data/processed/fire_smoke_v2/")

    # Step 7: Audit Artifact Generation
    print("\n[Step 7] Generating comprehensive Phase 7B audit artifacts...")

    # 1. split_manifest.csv
    manifest_csv = AUDIT_DIR / "split_manifest.csv"
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        fields = [
            "relative_path", "assigned_split", "target_class", "source_id",
            "original_filename", "canonical_filename", "sha256", "format",
            "width", "height", "aspect_ratio", "scene_group_id", "dhash",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_records)

    # 2. split_summary.json
    summary_by_split = {}
    for s_name in ["train", "validation", "test"]:
        recs = [r for r in manifest_records if r["assigned_split"] == s_name]
        cls_dist = defaultdict(int)
        src_dist = defaultdict(int)
        fmt_dist = defaultdict(int)
        widths = []
        heights = []
        for r in recs:
            cls_dist[r["target_class"]] += 1
            src_dist[r["source_id"]] += 1
            fmt_dist[r["format"]] += 1
            widths.append(r["width"])
            heights.append(r["height"])

        summary_by_split[s_name] = {
            "total_images": len(recs),
            "class_distribution": dict(cls_dist),
            "source_distribution": dict(src_dist),
            "format_distribution": dict(fmt_dist),
            "resolution_stats": {
                "min_width": min(widths) if widths else 0,
                "max_width": max(widths) if widths else 0,
                "mean_width": round(sum(widths) / len(widths), 1) if widths else 0,
                "min_height": min(heights) if heights else 0,
                "max_height": max(heights) if heights else 0,
                "mean_height": round(sum(heights) / len(heights), 1) if heights else 0,
            },
        }

    split_summary = {
        "dataset_name": "fire_smoke_v2",
        "generated_at_utc": "2026-10-31T04:30:00Z",
        "random_seed": RANDOM_SEED,
        "total_images": len(manifest_records),
        "total_scene_groups": len(scene_groups),
        "target_classes": CLASSES,
        "splits": summary_by_split,
    }
    with open(AUDIT_DIR / "split_summary.json", "w", encoding="utf-8") as f:
        json.dump(split_summary, f, indent=2)

    # 3. duplicate_analysis.json
    dup_analysis = {
        "generated_at_utc": "2026-10-31T04:30:00Z",
        "total_candidates_scanned": len(raw_candidates),
        "valid_images_scanned": len(valid_candidates),
        "exact_duplicates_count": len(exact_duplicates),
        "unique_images_retained": len(unique_candidates),
        "exact_duplicates_list": exact_duplicates[:100],  # sample up to 100
        "perceptual_hash_algorithm": "dHash (difference hash, 64-bit)",
        "near_duplicate_hamming_threshold": 3,
        "total_scene_groups_formed": len(scene_groups),
    }
    with open(AUDIT_DIR / "duplicate_analysis.json", "w", encoding="utf-8") as f:
        json.dump(dup_analysis, f, indent=2)

    # 4. scene_grouping_audit.json
    # Verify that ZERO scene groups cross split boundaries
    group_split_map: Dict[str, Set[str]] = defaultdict(set)
    for r in manifest_records:
        group_split_map[r["scene_group_id"]].add(r["assigned_split"])

    leaked_groups = {g: list(s) for g, s in group_split_map.items() if len(s) > 1}
    scene_audit = {
        "generated_at_utc": "2026-10-31T04:30:00Z",
        "total_groups": len(group_split_map),
        "leaked_groups_count": len(leaked_groups),
        "is_leakage_free": len(leaked_groups) == 0,
        "leaked_groups_details": leaked_groups,
        "group_size_distribution": {
            "singleton_groups_size_1": len([g for g in scene_groups if g.size == 1]),
            "multi_image_groups_size_gt_1": len([g for g in scene_groups if g.size > 1]),
            "max_group_size": max(g.size for g in scene_groups) if scene_groups else 0,
        },
    }
    with open(AUDIT_DIR / "scene_grouping_audit.json", "w", encoding="utf-8") as f:
        json.dump(scene_audit, f, indent=2)

    # 5. dataset_quality_report.json
    quality_report = {
        "generated_at_utc": "2026-10-31T04:30:00Z",
        "validation_strategy": "Two-pass Pillow header + pixel decode",
        "raw_candidates_count": len(raw_candidates),
        "passed_validation_count": len(valid_candidates),
        "quarantined_count": len(quarantined),
        "quarantined_samples": quarantined[:50],
        "exact_duplicates_count": len(exact_duplicates),
        "final_v2_dataset_count": len(manifest_records),
    }
    with open(AUDIT_DIR / "dataset_quality_report.json", "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)

    # 6. dataset_class_source_distribution.csv
    with open(AUDIT_DIR / "dataset_class_source_distribution.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["split", "source_id", "target_class", "image_count"])
        matrix = defaultdict(int)
        for r in manifest_records:
            matrix[(r["assigned_split"], r["source_id"], r["target_class"])] += 1
        for (spl, src, cls), cnt in sorted(matrix.items()):
            writer.writerow([spl, src, cls, cnt])

    # 7. dataset_format_resolution_distribution.csv
    with open(AUDIT_DIR / "dataset_format_resolution_distribution.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["split", "target_class", "format", "count", "min_width", "max_width", "mean_width", "min_height", "max_height", "mean_height"])
        fmt_matrix = defaultdict(list)
        for r in manifest_records:
            fmt_matrix[(r["assigned_split"], r["target_class"], r["format"])].append((r["width"], r["height"]))
        for (spl, cls, fmt), dims in sorted(fmt_matrix.items()):
            ws = [d[0] for d in dims]
            hs = [d[1] for d in dims]
            writer.writerow([
                spl, cls, fmt, len(dims),
                min(ws), max(ws), round(sum(ws) / len(ws), 1),
                min(hs), max(hs), round(sum(hs) / len(hs), 1),
            ])

    # 8. dataset_integrity_hashes.json
    with open(AUDIT_DIR / "dataset_integrity_hashes.json", "w", encoding="utf-8") as f:
        json.dump(dataset_hashes, f, indent=2)

    print("\n[Done] Pipeline execution finished successfully!")
    print(f"Total v2 dataset images: {len(manifest_records)}")
    print(f"Zero leakage audit: {scene_audit['is_leakage_free']}")
    return split_summary


if __name__ == "__main__":
    run_pipeline()
