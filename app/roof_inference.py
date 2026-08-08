from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.transforms import functional as TF
from torchvision.models import resnet18

from .config import Config


# ================================================================
# CONFIGURATION
#
# Candidate model paths (models/ for a frozen deployment copy, falling
# back to the training pipeline's own output directory during
# development) are defined once in Config - see app/config.py.
# ================================================================

MODEL_PATH_CANDIDATES = Config.ROOF_MODEL_PATH_CANDIDATES

# Human-readable labels for the raw class slugs stored in the checkpoint.
FEATURE_LABELS = {
    "chimney": "Chimney",
    "roof-vegetation": "Roof vegetation",
    "rooftop-hvac": "Rooftop HVAC",
    "skylight": "Skylight",
    "solar": "Solar panels",
}

# Cached across requests so the checkpoint is only loaded once per process.
_MODEL_CACHE: dict[str, Any] = {}


# ================================================================
# PREPROCESSING
# ================================================================
#
# This must exactly mirror the eval_transform pipeline used in
# yolo_finetune.ipynb ("IMAGE PREPROCESSING" cell), or the model will
# see different inputs than it was trained/validated on.


class PadToSquare:
    """Pad an image to a square while preserving its aspect ratio."""

    def __call__(self, image):
        width, height = image.size
        max_side = max(width, height)

        pad_left = (max_side - width) // 2
        pad_right = max_side - width - pad_left

        pad_top = (max_side - height) // 2
        pad_bottom = max_side - height - pad_top

        return TF.pad(
            image,
            [pad_left, pad_top, pad_right, pad_bottom],
            fill=0,
        )


def _build_transform(checkpoint: dict) -> transforms.Compose:
    image_size = checkpoint["image_size"]

    return transforms.Compose(
        [
            PadToSquare(),
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=checkpoint["imagenet_mean"],
                std=checkpoint["imagenet_std"],
            ),
        ]
    )


# ================================================================
# MODEL LOADING
# ================================================================


def _resolve_model_path() -> Path:
    for candidate in MODEL_PATH_CANDIDATES:
        if candidate.exists():
            return candidate

    searched = "\n".join(f"  - {candidate}" for candidate in MODEL_PATH_CANDIDATES)

    raise FileNotFoundError(
        "Roof classification model not found. Looked in:\n" + searched
    )


def _load_checkpoint() -> dict:
    model_path = _resolve_model_path()

    return torch.load(
        model_path,
        map_location="cpu",
        weights_only=False,
    )


def _load_model() -> tuple[nn.Module, dict, transforms.Compose]:
    """Load (and cache) the model, its checkpoint metadata, and its transform."""

    if "model" in _MODEL_CACHE:
        return (
            _MODEL_CACHE["model"],
            _MODEL_CACHE["checkpoint"],
            _MODEL_CACHE["transform"],
        )

    checkpoint = _load_checkpoint()

    architecture = checkpoint.get("architecture")

    if architecture != "resnet18":
        raise ValueError(
            "Unsupported architecture in roof model checkpoint: "
            f"{architecture!r}"
        )

    classes = checkpoint["classes"]

    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    transform = _build_transform(checkpoint)

    _MODEL_CACHE["model"] = model
    _MODEL_CACHE["checkpoint"] = checkpoint
    _MODEL_CACHE["transform"] = transform

    return model, checkpoint, transform


# ================================================================
# PUBLIC ENTRY POINT
# ================================================================


def classify_roof(image_path: Path) -> dict:
    """
    Run the fine-tuned rooftop multi-label classifier on one masked roof
    image (as produced by process_roof_imagery.generate_masked_roof_image)
    and return per-class probabilities plus the detected features.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Roof image not found: {image_path}")

    model, checkpoint, transform = _load_model()
    classes = checkpoint["classes"]
    threshold = checkpoint.get("threshold", 0.5)

    with Image.open(image_path) as image:
        # Masked-out pixels outside the building footprint are already
        # black with alpha=0 (see process_roof_imagery.create_roof_mask),
        # matching how the training images were prepared, so a plain RGB
        # conversion reproduces the same input the model was trained on.
        image = image.convert("RGB")
        tensor = transform(image).unsqueeze(0)

    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.sigmoid(logits).squeeze(0).tolist()

    predictions = {
        label: {
            "label": FEATURE_LABELS.get(label, label),
            "probability": round(float(probability), 4),
            "detected": probability >= threshold,
        }
        for label, probability in zip(classes, probabilities)
    }

    detected_features = [
        predictions[label]["label"]
        for label in classes
        if predictions[label]["detected"]
    ]

    return {
        "threshold": threshold,
        "predictions": predictions,
        "detected_features": detected_features,
    }
