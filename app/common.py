from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torchvision import transforms
from torchvision.transforms import functional as TF
from torchvision.models import resnet18


# ================================================================
# PREPROCESSING
# ================================================================
#
# Shared by every roof-image model (rooftop features, roof type, roof
# material, ...) - confirmed to be the same input pipeline used for all
# of them: pad to square, resize, normalize with ImageNet stats. This
# must exactly mirror eval_transform in the training notebooks, or a
# model sees different inputs than it was trained/validated on.


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


def build_transform(checkpoint: dict) -> transforms.Compose:
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
# CHECKPOINT LOADING
# ================================================================


def _require_key(checkpoint: dict, key: str, model_name: str) -> Any:
    """
    Fetch a required checkpoint key, or fail with a clear, specific error
    instead of a bare KeyError three frames down. Every model we've
    exported so far stores its own config (classes, image_size,
    normalization stats, ...) alongside the weights, so if a checkpoint
    is missing one of these, something about how it was exported doesn't
    match what this loader expects - worth knowing immediately, not
    guessing around.
    """

    if key not in checkpoint:
        available = ", ".join(sorted(checkpoint.keys()))
        raise KeyError(
            f"{model_name} checkpoint is missing expected key {key!r}. "
            f"Keys found: [{available}]. "
            "If this model was exported with a different structure than "
            "the rooftop-features model, this loader needs updating to "
            "match it."
        )

    return checkpoint[key]


def resolve_model_path(candidates: list[Path], model_name: str) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = "\n".join(f"  - {candidate}" for candidate in candidates)

    raise FileNotFoundError(
        f"{model_name} model not found. Looked in:\n{searched}"
    )


def load_checkpoint(candidates: list[Path], model_name: str) -> dict:
    model_path = resolve_model_path(candidates, model_name)

    return torch.load(
        model_path,
        map_location="cpu",
        weights_only=False,
    )


def build_resnet18(checkpoint: dict, model_name: str) -> nn.Module:
    """Build and load a ResNet18 classifier head sized to the checkpoint's classes."""

    architecture = checkpoint.get("architecture")

    if architecture != "resnet18":
        raise ValueError(
            f"Unsupported architecture in {model_name} checkpoint: "
            f"{architecture!r}"
        )

    classes = _require_key(checkpoint, "classes", model_name)

    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(
        _require_key(checkpoint, "model_state_dict", model_name)
    )
    model.eval()

    return model


class ModelCache:
    """
    Per-model in-memory cache so repeated inference calls in the same
    process don't reload weights from disk every time. Each classifier
    module gets its own instance - they must not share one, or loading
    the roof-material model would evict the rooftop-features model (and
    vice versa) on every alternating request.
    """

    def __init__(self, model_name: str, candidates: list[Path]):
        self.model_name = model_name
        self.candidates = candidates
        self._cache: dict[str, Any] = {}

    def get(self) -> tuple[nn.Module, dict, transforms.Compose]:
        if "model" in self._cache:
            return (
                self._cache["model"],
                self._cache["checkpoint"],
                self._cache["transform"],
            )

        checkpoint = load_checkpoint(self.candidates, self.model_name)
        model = build_resnet18(checkpoint, self.model_name)
        transform = build_transform(checkpoint)

        self._cache["model"] = model
        self._cache["checkpoint"] = checkpoint
        self._cache["transform"] = transform

        return model, checkpoint, transform
