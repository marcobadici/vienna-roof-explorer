from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib

# Flask processes imagery in a worker thread. Use a non-interactive backend
# so Matplotlib never tries to create Tkinter GUI objects.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from PIL import Image
from rasterio.mask import mask
from rasterio.plot import show
from rasterio.windows import from_bounds
from shapely.geometry import mapping

from .config import Config


# ================================================================
# CONFIGURATION
#
# All paths and the orthophoto URL are aliased from the central Config -
# see app/config.py. Everything below this block is unchanged from before.
# ================================================================

# Input
BUILDING_FILE = Config.SELECTED_BUILDING_FILE

# Temporary complete tile download
TEMP_TILE_FILE = Config.TEMP_TILE_FILE

# Outputs
ROOF_CROP_FILE = Config.ROOF_CROP_FILE
ROOF_OVERLAY_FILE = Config.ROOF_OVERLAY_FILE
ROOF_MASKED_TIF = Config.ROOF_MASKED_TIF
ROOF_MASKED_PNG = Config.ROOF_MASKED_PNG

BUFFER_METERS = Config.BUFFER_METERS
ZOOM_LEVEL = Config.ORTHOPHOTO_ZOOM_LEVEL

ORTHOPHOTO_URL = Config.ORTHOPHOTO_URL


def load_selected_building() -> gpd.GeoDataFrame:
    """Load and validate the selected building geometry."""

    if not BUILDING_FILE.exists():
        raise FileNotFoundError(
            f"Selected building not found: {BUILDING_FILE}"
        )

    building = gpd.read_file(BUILDING_FILE)

    if building.empty:
        raise ValueError(
            "The selected building file is empty."
        )

    if building.crs is None:
        building = building.set_crs("EPSG:4326")

    valid_geometry = (
        building.geometry.notna()
        & ~building.geometry.is_empty
    )

    building = building[valid_geometry].copy()

    if building.empty:
        raise ValueError(
            "The selected building contains no valid geometry."
        )

    return building


def download_roof_crop(
    building: gpd.GeoDataFrame,
) -> None:
    """
    Download Vienna orthophoto tiles and crop them precisely
    around the selected building.
    """

    building_3857 = building.to_crs("EPSG:3857")

    buffered_geometry = (
        building_3857.geometry.buffer(BUFFER_METERS)
    )

    west, south, east, north = (
        buffered_geometry.total_bounds
    )

    row = building.iloc[0]
    building_id = (
        row.get("official_building_id")
        or row.get("building_key")
        or row.get("address_code")
        or "unknown"
    )

    print("Downloading Vienna orthophoto...")
    print(f"Building ID: {building_id}")
    print()
    print("Requested crop bounds:")
    print(f"Width:  {east - west:.2f} metres")
    print(f"Height: {north - south:.2f} metres")

    ctx.bounds2raster(
        west,
        south,
        east,
        north,
        path=str(TEMP_TILE_FILE),
        zoom=ZOOM_LEVEL,
        source=ORTHOPHOTO_URL,
        ll=False,
        n_connections=1,
    )

    try:
        with rasterio.open(TEMP_TILE_FILE) as source:
            window = from_bounds(
                west,
                south,
                east,
                north,
                transform=source.transform,
            )

            window = (
                window
                .round_offsets()
                .round_lengths()
            )

            image = source.read(
                window=window
            )

            profile = source.profile.copy()

            profile.update(
                width=image.shape[2],
                height=image.shape[1],
                transform=source.window_transform(
                    window
                ),
            )

        with rasterio.open(
            ROOF_CROP_FILE,
            "w",
            **profile,
        ) as destination:
            destination.write(image)

    finally:
        TEMP_TILE_FILE.unlink(
            missing_ok=True
        )

    print()
    print("Exact roof crop saved:")
    print(ROOF_CROP_FILE)
    print(
        f"Image size: "
        f"{image.shape[2]} × {image.shape[1]} pixels"
    )


def create_roof_overlay(
    building: gpd.GeoDataFrame,
) -> None:
    """
    Draw the official building boundary over the orthophoto.
    """

    with rasterio.open(ROOF_CROP_FILE) as raster:
        projected_building = building.to_crs(
            raster.crs
        )

        figure, axis = plt.subplots(
            figsize=(7, 7)
        )

        show(
            raster,
            ax=axis,
        )

        # Light fill + strong boundary make the selected roof-plan proxy
        # easy to verify visually against the orthophoto.
        projected_building.plot(
            ax=axis,
            facecolor="red",
            edgecolor="none",
            alpha=0.12,
        )

        projected_building.boundary.plot(
            ax=axis,
            edgecolor="red",
            linewidth=2.5,
        )

        axis.set_title(
            "Roof plan outline (official FMZK footprint approximation)",
            fontsize=10,
            pad=8,
        )
        axis.set_axis_off()

        figure.savefig(
            ROOF_OVERLAY_FILE,
            dpi=200,
            bbox_inches="tight",
            pad_inches=0,
        )

        plt.close(figure)

    print()
    print("Roof overlay saved:")
    print(ROOF_OVERLAY_FILE)


def create_roof_mask(
    building: gpd.GeoDataFrame,
) -> None:
    """
    Mask everything outside the selected building polygon.
    """

    with rasterio.open(ROOF_CROP_FILE) as source:
        projected_building = building.to_crs(
            source.crs
        )

        geometries = [
            mapping(geometry)
            for geometry in projected_building.geometry
            if (
                geometry is not None
                and not geometry.is_empty
            )
        ]

        if not geometries:
            raise ValueError(
                "No valid building geometries are "
                "available for masking."
            )

        masked_image, masked_transform = mask(
            source,
            geometries,
            crop=False,
            filled=True,
            nodata=0,
        )

        profile = source.profile.copy()

        profile.update(
            height=masked_image.shape[1],
            width=masked_image.shape[2],
            transform=masked_transform,
            nodata=0,
        )

    # Save georeferenced masked image
    with rasterio.open(
        ROOF_MASKED_TIF,
        "w",
        **profile,
    ) as destination:
        destination.write(masked_image)

    # Prepare RGB image
    if masked_image.shape[0] >= 3:
        rgb = masked_image[:3]
    else:
        rgb = np.repeat(
            masked_image[:1],
            3,
            axis=0,
        )

    rgb = np.moveaxis(
        rgb,
        0,
        -1,
    )

    # PIL normally expects uint8 image values
    if rgb.dtype != np.uint8:
        rgb = np.clip(
            rgb,
            0,
            255,
        ).astype(np.uint8)

    # Transparent outside the building polygon
    alpha = np.where(
        np.any(rgb != 0, axis=2),
        255,
        0,
    ).astype(np.uint8)

    rgba = np.dstack(
        (rgb, alpha)
    )

    Image.fromarray(
        rgba,
        mode="RGBA",
    ).save(ROOF_MASKED_PNG)

    print()
    print("Masked roof files saved:")
    print(ROOF_MASKED_TIF)
    print(ROOF_MASKED_PNG)


def generate_masked_roof_image(
    building: gpd.GeoDataFrame,
) -> Path:
    """
    Download orthophoto imagery for `building`, save a visual roof-outline
    overlay for inspection/submission evidence, and produce the masked PNG
    used for model inference.

    The overlay uses the official FMZK building footprint as a plan-view
    roof approximation; it is not an image-segmentation result.
    """

    download_roof_crop(building)
    create_roof_overlay(building)
    create_roof_mask(building)

    return ROOF_MASKED_PNG


def main() -> None:
    building = load_selected_building()

    download_roof_crop(
        building
    )

    create_roof_overlay(
        building
    )

    create_roof_mask(
        building
    )

    print()
    print("=" * 60)
    print("ROOF IMAGERY PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Roof crop:     {ROOF_CROP_FILE.name}")
    print(f"Overlay:       {ROOF_OVERLAY_FILE.name}")
    print(f"Masked TIFF:   {ROOF_MASKED_TIF.name}")
    print(f"Masked PNG:    {ROOF_MASKED_PNG.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()