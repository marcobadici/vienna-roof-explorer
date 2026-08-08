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
    Run the fine-tuned roof-material classifier on one masked roof image
    and return the predicted material plus the full class distribution.

    UNVERIFIED ASSUMPTION - no checkpoint was available to introspect
    when this was written (unlike classify_roof() in features.py, which
    was tested against the real weights). This assumes single-label
    softmax classification: one dominant material per roof, competing
    probabilities that sum to 1. That's the natural framing for "roof
    material" and matches how it came up in conversation, but if the
    model was actually trained multi-label (e.g. distinct materials
    across different sections of a complex roof), this needs to switch
    to sigmoid + per-class threshold instead, matching classify_roof().

    Also unverified: the checkpoint uses the same self-describing
    structure as the rooftop-features model (classes / image_size /
    imagenet_mean / imagenet_std / architecture / model_state_dict). If
    it doesn't, common.load_checkpoint() will raise a clear KeyError
    naming the missing field rather than failing silently or guessing.
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
