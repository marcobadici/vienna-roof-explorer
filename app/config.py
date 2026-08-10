import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ================================================================
# PROJECT LAYOUT
# ================================================================
#
# Every path used anywhere in the app is defined here, once. No other
# module should compute its own BASE_DIR / Path(__file__).parent - that's
# what caused the "which folder is this actually running from" confusion
# during development. If a path is wrong, there's exactly one place to
# fix it.

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config:
    PROJECT_ROOT = PROJECT_ROOT

    # ------------------------------------------------------------
    # Generated map (build artifact, not source - see build_map.py)
    # ------------------------------------------------------------
    MAP_OUTPUT_FILE = (
        PROJECT_ROOT / "app" / "static" / "map"
        / "vienna_dynamic_buildings_map.html"
    )

    # ------------------------------------------------------------
    # Runtime data - generated per building selection, not committed to
    # version control. Override with the RUNTIME_DATA_DIR env var if you
    # ever need per-worker or per-session isolation.
    # ------------------------------------------------------------
    RUNTIME_DATA_DIR = Path(
        os.environ.get(
            "RUNTIME_DATA_DIR",
            PROJECT_ROOT / "data" / "runtime",
        )
    )

    SELECTED_BUILDING_FILE = RUNTIME_DATA_DIR / "selected_building.geojson"
    ROOF_CROP_FILE = RUNTIME_DATA_DIR / "selected_roof.tif"
    ROOF_OVERLAY_FILE = RUNTIME_DATA_DIR / "selected_roof_overlay.png"
    ROOF_MASKED_TIF = RUNTIME_DATA_DIR / "selected_roof_masked.tif"
    ROOF_MASKED_PNG = RUNTIME_DATA_DIR / "selected_roof_masked.png"
    TEMP_TILE_FILE = RUNTIME_DATA_DIR / "_downloaded_tiles.tif"

    # Optional local BEV DLM Bauwerke GeoPackage - a persistent data asset
    # (not a per-request runtime file), so it lives under data/ directly
    # rather than data/runtime/. Absent by default; official_data.py
    # reports "not_configured" for this source until it's dropped in.
    BEV_GPKG_PATH = Path(
        os.environ.get(
            "BEV_GPKG_PATH",
            PROJECT_ROOT / "data" / "bev_bauwerke_vienna.gpkg",
        )
    )

    # ------------------------------------------------------------
    # Roof classification models
    #
    # Each model is checked in two locations, in order: a frozen copy in
    # models/ (production), then the training pipeline's own output
    # directory (convenient during development so you don't have to copy
    # the file after every retrain).
    # ------------------------------------------------------------
    MODEL_DIR = Path(
        os.environ.get("MODEL_DIR", PROJECT_ROOT / "models")
    )

    ROOF_FEATURES_MODEL_FILENAME = "roof_multilabel_resnet18.pth"
    ROOF_FEATURES_MODEL_PATH_CANDIDATES = [
        MODEL_DIR / ROOF_FEATURES_MODEL_FILENAME,
        PROJECT_ROOT / "training" / "outputs" / "roof_multilabel" / "models"
        / ROOF_FEATURES_MODEL_FILENAME,
    ]

    ROOF_MATERIAL_MODEL_FILENAME = "roof_material_resnet18.pth"
    ROOF_MATERIAL_MODEL_PATH_CANDIDATES = [
        MODEL_DIR / ROOF_MATERIAL_MODEL_FILENAME,
        PROJECT_ROOT / "training" / "outputs" / "roof_material" / "models"
        / ROOF_MATERIAL_MODEL_FILENAME,
    ]

    # ------------------------------------------------------------
    # Vienna open-data / imagery sources
    # ------------------------------------------------------------
    WFS_URL = os.environ.get(
        "VIENNA_WFS_URL",
        "https://data.wien.gv.at/daten/geo",
    )
    BUILDING_LAYER = "ogdwien:FMZKBKMOGD"

    ORTHOPHOTO_URL = (
        "https://mapsneu.wien.gv.at/wmts/lb/farbe/"
        "google3857/{z}/{y}/{x}.jpeg"
    )

    WGS84 = "EPSG:4326"
    METRIC_CRS = "EPSG:32633"  # UTM 33N; appropriate for Vienna

    MAP_CENTER = [48.1657, 16.2850]

    BUFFER_METERS = 1
    ORTHOPHOTO_ZOOM_LEVEL = 20

    # ------------------------------------------------------------
    # Server
    # ------------------------------------------------------------
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"


def ensure_runtime_dirs() -> None:
    """Create any writable directories the app needs on first run."""

    Config.RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.MAP_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
