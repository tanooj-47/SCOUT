"""
backend/app/intelligence/adapters/vision_adapter.py
Computer Vision Subsystem Adapter for Milestone 07 Champion BaselineCNN.
Safely loads checkpoint, executes deterministic letterbox preprocessing,
and maps class probabilities with zero model alteration.
"""

from io import BytesIO
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
from PIL import Image
import torch

from app.intelligence.evidence import EvidenceCollector
from app.intelligence.exceptions import VisionInferenceError
from app.intelligence.schemas import CoordinateLocation, EvidenceItem
from ml.config import CLASS_TO_IDX, IDX_TO_CLASS, PROJECT_ROOT
from ml.data.transforms import get_eval_transforms
from ml.models.baseline_cnn import BaselineCNN
from ml.training.checkpoints import CheckpointIntegrityError, CheckpointManager

logger = logging.getLogger(__name__)

# Primary and fallback paths for champion model checkpoint
PRIMARY_CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts" / "checkpoints" / "m07_phase7c_v2" / "baseline_cnn_best.pt"
)
FALLBACK_CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts" / "checkpoints" / "baseline_cnn_best.pt"
)


class VisionModelAdapter:
    """
    Adapter encapsulating inference with M07 BaselineCNN.
    Enforces deterministic evaluation transforms (get_eval_transforms) and eval mode.
    """

    def __init__(self, checkpoint_path: Optional[Union[str, Path]] = None) -> None:
        self.requested_checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self._model: Optional[BaselineCNN] = None
        self._checkpoint_metadata: Dict[str, Any] = {}
        self._resolved_checkpoint_path: Optional[Path] = None
        self._transform = get_eval_transforms()

    def _resolve_checkpoint_path(self) -> Path:
        """Resolves the best available checkpoint path."""
        candidates = []
        if self.requested_checkpoint_path:
            candidates.append(self.requested_checkpoint_path)
        candidates.extend([PRIMARY_CHECKPOINT_PATH, FALLBACK_CHECKPOINT_PATH])

        for p in candidates:
            if p.exists() and p.is_file():
                return p

        raise FileNotFoundError(
            f"BaselineCNN champion checkpoint not found. Inspected: {[str(c) for c in candidates]}"
        )

    def load_model(self) -> BaselineCNN:
        """
        Lazily loads and validates the BaselineCNN champion model checkpoint on CPU.
        """
        if self._model is not None:
            return self._model

        checkpoint_path = self._resolve_checkpoint_path()
        logger.info(f"Loading BaselineCNN champion model from {checkpoint_path}")

        try:
            mgr = CheckpointManager()
            ckpt = mgr.load_checkpoint(checkpoint_path, is_trusted=True)
            self._checkpoint_metadata = {
                k: v for k, v in ckpt.items() if k not in ("model_state_dict", "optimizer_state_dict")
            }

            model = BaselineCNN(num_classes=len(CLASS_TO_IDX))
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()

            self._model = model
            self._resolved_checkpoint_path = checkpoint_path
            return self._model
        except Exception as exc:
            logger.error(f"Failed to load vision model checkpoint from {checkpoint_path}: {exc}")
            raise VisionInferenceError(f"Model initialization error: {exc}") from exc

    def predict_image(
        self,
        image_input: Union[str, Path, bytes, Image.Image],
    ) -> Dict[str, float]:
        """
        Executes inference on an image source (filepath, raw bytes, or PIL Image).
        Returns class probabilities dictionary: {"fire": float, "neutral": float, "smoke": float}.
        """
        model = self.load_model()

        # 1. Load into PIL RGB Image
        pil_img: Image.Image
        try:
            if isinstance(image_input, Image.Image):
                pil_img = image_input.convert("RGB")
            elif isinstance(image_input, (str, Path)):
                img_path = Path(image_input)
                if not img_path.exists() or not img_path.is_file():
                    raise FileNotFoundError(f"Image file does not exist: {img_path}")
                pil_img = Image.open(img_path).convert("RGB")
            elif isinstance(image_input, (bytes, bytearray)):
                pil_img = Image.open(BytesIO(image_input)).convert("RGB")
            else:
                raise ValueError(f"Unsupported image input type: {type(image_input)}")
        except Exception as exc:
            raise VisionInferenceError(f"Failed to read or decode image input: {exc}") from exc

        # 2. Preprocess with M07 deterministic letterbox transform
        try:
            tensor = self._transform(pil_img)  # Shape [3, 224, 224]
            batch_tensor = tensor.unsqueeze(0)  # Shape [1, 3, 224, 224]
        except Exception as exc:
            raise VisionInferenceError(f"Image preprocessing transformation failed: {exc}") from exc

        # 3. Model forward pass
        try:
            with torch.no_grad():
                logits = model(batch_tensor)  # Shape [1, 3]
                probs = torch.softmax(logits, dim=1).squeeze(0)  # Shape [3]
        except Exception as exc:
            raise VisionInferenceError(f"Model evaluation pass failed: {exc}") from exc

        # 4. Map logits to class names
        result: Dict[str, float] = {}
        for idx in range(len(probs)):
            cls_name = IDX_TO_CLASS.get(idx, f"class_{idx}")
            result[cls_name] = round(float(probs[idx].item()), 4)

        return result

    def collect_evidence(
        self,
        image_input: Optional[Union[str, Path, bytes, Image.Image]],
        location: Optional[CoordinateLocation] = None,
    ) -> EvidenceItem:
        """
        Runs vision evaluation and returns a typed EvidenceItem.
        If image_input is None or invalid, returns an unavailable EvidenceItem.
        """
        if image_input is None:
            return EvidenceCollector.create_unavailable_cv_evidence("No image provided in observation")

        try:
            probabilities = self.predict_image(image_input)
            ckpt_str = str(self._resolved_checkpoint_path or "baseline_cnn_best.pt")
            return EvidenceCollector.create_cv_evidence(
                probabilities=probabilities,
                model_name="BaselineCNN",
                checkpoint_path=ckpt_str,
                location=location,
            )
        except Exception as exc:
            logger.warning(f"Vision inference failed; recording unavailable evidence: {exc}")
            return EvidenceCollector.create_unavailable_cv_evidence(str(exc))
