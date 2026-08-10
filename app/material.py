from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image

from . import common
from .config import Config


_cache = common.ModelCache(
    model_name="Roof material",
    candidates=Config.ROOF_MATERIAL_MODEL_PATH_CANDIDATES,
)

def classify_roof_material(image_path: Path) -> dict:
    """
    Run the fine-tuned roof-material multiclass classifier on one
    masked roof image.

    The model applies softmax across the checkpoint-defined material
    classes and returns the highest-probability class together with
    the full class-probability distribution.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Roof image not found: {image_path}")

    model, checkpoint, transform = _cache.get()
    classes = checkpoint["classes"]

    with Image.open(image_path) as image:
        image = image.convert("RGB")
        tensor = transform(image).unsqueeze(0)

    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0).tolist()

    class_probabilities = {
        label: round(float(probability), 4)
        for label, probability in zip(classes, probabilities)
    }

    predicted_class = max(class_probabilities, key=class_probabilities.get)

    return {
        "material": predicted_class,
        "confidence": class_probabilities[predicted_class],
        "class_probabilities": class_probabilities,
    }
