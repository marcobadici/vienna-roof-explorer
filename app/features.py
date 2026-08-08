from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image

from . import common
from .config import Config


# Human-readable labels for the raw class slugs stored in the checkpoint.
FEATURE_LABELS = {
    "chimney": "Chimney",
    "roof-vegetation": "Roof vegetation",
    "rooftop-hvac": "Rooftop HVAC",
    "skylight": "Skylight",
    "solar": "Solar panels",
}

_cache = common.ModelCache(
    model_name="Rooftop features",
    candidates=Config.ROOF_FEATURES_MODEL_PATH_CANDIDATES,
)


def classify_roof(image_path: Path) -> dict:
    """
    Run the fine-tuned rooftop multi-label classifier on one masked roof
    image (as produced by roof_imagery.generate_masked_roof_image) and
    return per-class probabilities plus the detected features.

    Multi-label: chimney, vegetation, HVAC, skylight, and solar can all
    be present on the same roof independently, so each class gets its
    own sigmoid probability and threshold rather than one shared softmax.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Roof image not found: {image_path}")

    model, checkpoint, transform = _cache.get()
    classes = checkpoint["classes"]
    threshold = checkpoint.get("threshold", 0.5)

    with Image.open(image_path) as image:
        # Masked-out pixels outside the building footprint are already
        # black with alpha=0 (see roof_imagery.create_roof_mask), matching
        # how the training images were prepared, so a plain RGB
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
