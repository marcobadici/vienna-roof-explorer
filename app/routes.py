import json
import math
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd
import requests

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    send_file,
)

from . import roof_imagery
from . import features as roof_features
from . import material as roof_material
from .official_data import collect_official_building_data


bp = Blueprint(
    "main",
    __name__,
)


# ================================================================
# GENERIC HELPERS
# ================================================================


def clean_identifier(value) -> str | None:
    """Return a stable string representation for Vienna identifiers."""

    if value is None or pd.isna(value):
        return None

    try:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    return text or None


def join_unique(values: pd.Series) -> str | None:
    """Join unique non-null values while keeping the output JSON-friendly."""

    cleaned = {
        str(value).strip()
        for value in values
        if pd.notna(value) and str(value).strip()
    }

    if not cleaned:
        return None

    return ", ".join(sorted(cleaned))


def numeric_stat(values: pd.Series, operation: str) -> float | None:
    """Aggregate a numeric FMZK field while ignoring missing values."""

    numeric = pd.to_numeric(values, errors="coerce").dropna()

    if numeric.empty:
        return None

    if operation == "min":
        result = numeric.min()
    elif operation == "max":
        result = numeric.max()
    elif operation == "mean":
        result = numeric.mean()
    else:
        raise ValueError(f"Unsupported numeric operation: {operation}")

    return round(float(result), 2)


# ================================================================
# BUILDING PROCESSING
# ================================================================


def create_building_key(row: pd.Series) -> str:
    """Create one identifier for all FMZK parts of the same building."""

    address_code = clean_identifier(row.get("BW_GEB_ID"))

    if address_code:
        return f"BW_{address_code}"

    fmzk_id = clean_identifier(row.get("FMZK_ID"))
    return f"FMZK_{fmzk_id or 'unknown'}"


def group_building_parts(buildings: dict, wgs84: str, metric_crs: str) -> dict:
    """
    Merge FMZK building parts and retain useful official attributes.

    BW_GEB_ID is treated as the Vienna address/building reference code used
    by related official datasets, rather than as an arbitrary display ID.
    """

    features = buildings.get("features", [])

    if not features:
        return {
            "type": "FeatureCollection",
            "features": [],
        }

    building_parts = gpd.GeoDataFrame.from_features(
        features,
        crs=wgs84,
    )

    required_columns = {
        "BW_GEB_ID",
        "FMZK_ID",
        "LAYER",
        "geometry",
    }

    missing_columns = required_columns.difference(building_parts.columns)

    if missing_columns:
        raise RuntimeError(
            f"Missing expected FMZK fields: {sorted(missing_columns)}"
        )

    building_parts = building_parts[
        building_parts.geometry.notna()
        & ~building_parts.geometry.is_empty
    ].copy()

    if building_parts.empty:
        return {
            "type": "FeatureCollection",
            "features": [],
        }

    building_parts["building_key"] = building_parts.apply(
        create_building_key,
        axis=1,
    )

    building_parts["address_code"] = building_parts["BW_GEB_ID"].apply(
        clean_identifier
    )

    # Keep this alias for compatibility with the earlier frontend while using
    # the semantically clearer address_code everywhere new.
    building_parts["official_building_id"] = building_parts[
        "address_code"
    ].fillna("Not available")

    building_parts["polygon_id"] = building_parts["FMZK_ID"].apply(
        clean_identifier
    )

    # Ensure optional official FMZK fields exist so the code stays robust if
    # a particular service response omits one of them.
    optional_fields = [
        "BEZUG",
        "H_KLASSE",
        "F_KLASSE",
        "KLASSE_SUB",
        "O_KOTE",
        "U_KOTE",
        "HOEHE_DGM",
        "T_KOTE",
    ]

    for field in optional_fields:
        if field not in building_parts.columns:
            building_parts[field] = pd.NA

    grouped_records = []

    for building_key, group in building_parts.groupby(
        "building_key",
        sort=False,
    ):
        geometry = group.geometry.union_all()

        address_code = next(
            (
                value
                for value in group["address_code"]
                if value is not None and pd.notna(value)
            ),
            None,
        )

        eave_elevation = numeric_stat(group["O_KOTE"], "max")
        lower_overbuild = numeric_stat(group["U_KOTE"], "min")
        terrain_mean = numeric_stat(group["HOEHE_DGM"], "mean")
        terrain_min_edge = numeric_stat(group["T_KOTE"], "min")

        approx_eave_height = None
        if eave_elevation is not None and terrain_mean is not None:
            approx_eave_height = round(
                eave_elevation - terrain_mean,
                2,
            )

        grouped_records.append(
            {
                "building_key": building_key,
                "official_building_id": address_code or "Not available",
                "address_code": address_code,
                "polygon_id": join_unique(group["polygon_id"]),
                "LAYER": join_unique(group["LAYER"]),
                "part_count": int(len(group)),
                "height_class": join_unique(group["H_KLASSE"]),
                "feature_class": join_unique(group["F_KLASSE"]),
                "subclass": join_unique(group["KLASSE_SUB"]),
                "reference_code": join_unique(group["BEZUG"]),
                "eave_elevation_m": eave_elevation,
                "lower_overbuild_elevation_m": lower_overbuild,
                "terrain_elevation_m": terrain_mean,
                "lowest_terrain_edge_m": terrain_min_edge,
                "approx_eave_height_m": approx_eave_height,
                "geometry": geometry,
            }
        )

    grouped_buildings = gpd.GeoDataFrame(
        grouped_records,
        geometry="geometry",
        crs=wgs84,
    )

    # Footprint derived from the official FMZK geometry.
    grouped_metric = grouped_buildings.to_crs(metric_crs)
    grouped_buildings["footprint_area_m2"] = (
        grouped_metric.geometry.area.round(1)
    )

    return json.loads(grouped_buildings.to_json())


# ================================================================
# MAP
# ================================================================


@bp.get("/")
def show_map():
    """Serve the generated Folium map."""

    map_file = current_app.config["MAP_OUTPUT_FILE"]

    if not map_file.exists():
        return {
            "status": "error",
            "message": (
                f"Map file not found: {map_file}. "
                "Run python build_map.py first."
            ),
        }, 404

    response = send_file(map_file)
    response.headers["Cache-Control"] = "no-store"
    return response


# ================================================================
# BUILDING API
# ================================================================


@bp.get("/api/buildings")
def get_buildings():
    """Retrieve grouped FMZK buildings in the visible map bounding box."""

    wgs84 = current_app.config["WGS84"]

    try:
        west = float(request.args["west"])
        south = float(request.args["south"])
        east = float(request.args["east"])
        north = float(request.args["north"])
    except (KeyError, TypeError, ValueError):
        return {
            "status": "error",
            "message": "Invalid or missing bounding-box coordinates.",
        }, 400

    if west >= east or south >= north:
        return {
            "status": "error",
            "message": "The bounding box is invalid.",
        }, 400

    longitude_span = east - west
    latitude_span = north - south

    # Avoid accidental city-wide WFS requests.
    if longitude_span > 0.08 or latitude_span > 0.08:
        return {
            "status": "error",
            "message": "The requested area is too large. Zoom in further.",
        }, 400

    longitude_padding = longitude_span * 0.08
    latitude_padding = latitude_span * 0.08

    query_west = west - longitude_padding
    query_south = south - latitude_padding
    query_east = east + longitude_padding
    query_north = north + latitude_padding

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": current_app.config["BUILDING_LAYER"],
        "outputFormat": "application/json",
        "srsName": wgs84,
        "bbox": (
            f"{query_west},{query_south},"
            f"{query_east},{query_north},{wgs84}"
        ),
        "count": 5000,
    }

    try:
        response = requests.get(
            current_app.config["WFS_URL"],
            params=params,
            timeout=60,
        )
        response.raise_for_status()

        grouped_buildings = group_building_parts(
            response.json(),
            wgs84=wgs84,
            metric_crs=current_app.config["METRIC_CRS"],
        )

    except requests.RequestException as error:
        return {
            "status": "error",
            "message": f"Vienna WFS request failed: {error}",
        }, 502

    except (ValueError, RuntimeError) as error:
        return {
            "status": "error",
            "message": str(error),
        }, 500

    return jsonify(grouped_buildings)


# ================================================================
# SELECT BUILDING + COLLECT OFFICIAL DATA
# ================================================================


def _run_roof_ai() -> dict:
    """
    Download roof imagery for the just-saved selection once, mask it to
    the building footprint, and run every fine-tuned roof classifier on
    that same image - they all take identical input (confirmed), so
    there's no reason to re-download/re-mask per model.

    Each model's result is independent: if the roof-material model isn't
    in place yet (or fails for its own reasons), the rooftop-features
    result is unaffected, and vice versa. Only a shared failure - the
    roof image itself couldn't be produced - takes both down together.
    """

    try:
        building = roof_imagery.load_selected_building()
        roof_image_path = roof_imagery.generate_masked_roof_image(building)
    except Exception as error:
        shared_error = {
            "status": "error",
            "message": f"Roof imagery generation failed: {error}",
        }
        return {"features": shared_error, "material": shared_error}

    results = {}

    try:
        results["features"] = roof_features.classify_roof(roof_image_path)
        results["features"]["status"] = "success"
        results["features"]["score_type"] = "model_probability"
    except Exception as error:
        results["features"] = {
            "status": "error",
            "message": f"Rooftop-features inference failed: {error}",
        }

    try:
        results["material"] = roof_material.classify_roof_material(
            roof_image_path
        )
        results["material"]["status"] = "success"
        results["material"]["score_type"] = "model_probability"
    except Exception as error:
        results["material"] = {
            "status": "error",
            "message": f"Roof-material inference failed: {error}",
        }

    return results


def _build_roof_record(
    official: dict,
    fmzk_data: dict,
    roof_outline: dict,
    roof_ai: dict,
) -> dict:
    """
    Build the machine-readable roof record returned to the browser.

    The browser can download this object directly through the
    "Generate JSON" button. No file is written automatically when
    a building is merely clicked.
    """

    profile = official.get("profile") or {}
    identification = profile.get("identification") or {}
    geometry_elevation = profile.get("geometry_elevation") or {}
    roof_solar = profile.get("roof_solar") or {}

    def as_float(value):
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def usable_text(value):
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        if text.lower() in {
            "keine angabe",
            "ohne angabe",
            "k.a.",
            "unbekannt",
            "not available",
        }:
            return None

        return text

    mean_slope_deg = as_float(
        roof_solar.get("mean_roof_slope_deg")
    )

    projected_area_m2 = as_float(
        geometry_elevation.get("footprint_area_m2")
    )

    if projected_area_m2 is None:
        projected_area_m2 = as_float(
            fmzk_data.get("footprint_area_m2")
        )

    official_roof_type = usable_text(
        roof_solar.get("roof_type")
    )

    if official_roof_type:
        roof_type = official_roof_type
        roof_type_score = 1.0
        roof_type_kind = "official_source"
        roof_type_basis = (
            "Direct roof type from Stadt Wien "
            "Photovoltaik Potenzial 2022."
        )
    elif mean_slope_deg is not None:
        if mean_slope_deg <= 5:
            roof_type = "Flat"
            roof_type_score = 0.95
        elif mean_slope_deg <= 15:
            roof_type = "Low-slope"
            roof_type_score = 0.85
        else:
            roof_type = "Pitched"
            roof_type_score = 0.95

        roof_type_kind = "engineering_confidence"
        roof_type_basis = (
            "Derived from official mean roof slope "
            f"({mean_slope_deg:.1f}°)."
        )
    else:
        roof_type = None
        roof_type_score = None
        roof_type_kind = None
        roof_type_basis = None

    estimated_surface_area_m2 = None

    if (
        projected_area_m2 is not None
        and mean_slope_deg is not None
        and 0 <= mean_slope_deg < 85
    ):
        estimated_surface_area_m2 = round(
            projected_area_m2
            / math.cos(math.radians(mean_slope_deg)),
            1,
        )

    if projected_area_m2 is not None:
        projected_area_m2 = round(
            projected_area_m2,
            1,
        )

    if mean_slope_deg is not None:
        mean_slope_deg = round(
            mean_slope_deg,
            1,
        )

    # Keep only positive rooftop-feature detections in the exported JSON,
    # matching the clean presentation used in the sidebar.
    detected_features = {}

    feature_result = roof_ai.get("features") or {}

    if (
        feature_result.get("status") == "success"
        and isinstance(feature_result.get("predictions"), dict)
    ):
        for key, prediction in feature_result["predictions"].items():
            if not prediction.get("detected"):
                continue

            probability = as_float(
                prediction.get("probability")
            )

            detected_features[key] = {
                "label": prediction.get("label") or key,
                "model_probability": (
                    round(probability, 4)
                    if probability is not None
                    else None
                ),
            }

    material_result = roof_ai.get("material") or {}

    material = None
    material_probability = None

    if material_result.get("status") == "success":
        material = usable_text(
            material_result.get("material")
        )

        probability = as_float(
            material_result.get("confidence")
        )

        if probability is not None:
            material_probability = round(
                probability,
                4,
            )

    building_id = (
        identification.get("building_object_id")
        or fmzk_data.get("building_key")
        or fmzk_data.get("address_code")
    )

    return {
        "building_id": building_id,
        "address_code": (
            identification.get("address_code")
            or fmzk_data.get("address_code")
        ),
        "address": identification.get("address"),
        "sources_used": {
            "roof_outline": "Stadt Wien – Baukörpermodell / FMZK",
            "roof_slope_and_solar": (
                "Stadt Wien – Photovoltaik Potenzial 2022"
            ),
            "imagery": "Stadt Wien Orthophoto",
            "rooftop_features": "Fine-tuned ResNet18",
            "roof_material": "Fine-tuned ResNet18",
        },
        "roof": {
            "outline": roof_outline.get("geometry"),
            "outline_method": roof_outline.get("method"),
            "projected_area_m2": projected_area_m2,
            "estimated_surface_area_m2": (
                estimated_surface_area_m2
            ),
            "type": roof_type,
            "type_basis": roof_type_basis,
            "mean_slope_deg": mean_slope_deg,
            "material": material,
        },
        "solar_potential": {
            "annual_yield_kwh_m2a": (
                roof_solar.get("annual_yield_kwh_m2a")
            ),
            "pv_area_medium_m2": (
                roof_solar.get("pv_area_medium_m2")
            ),
            "pv_area_good_m2": (
                roof_solar.get("pv_area_good_m2")
            ),
            "pv_area_very_good_m2": (
                roof_solar.get("pv_area_very_good_m2")
            ),
            "theoretical_pv_capacity_kwp": (
                roof_solar.get("theoretical_pv_capacity_kwp")
            ),
        },
        "rooftop_features": detected_features,
        "confidence": {
            "roof_outline": {
                "score": roof_outline.get("confidence"),
                "kind": roof_outline.get(
                    "confidence_kind",
                    "engineering_confidence",
                ),
                "basis": roof_outline.get("confidence_basis"),
            },
            "projected_area": {
                "score": (
                    0.95
                    if projected_area_m2 is not None
                    else None
                ),
                "kind": "engineering_confidence",
                "basis": (
                    "Official FMZK footprint used as the "
                    "plan-view roof-area proxy."
                ),
            },
            "estimated_surface_area": {
                "score": (
                    0.75
                    if estimated_surface_area_m2 is not None
                    else None
                ),
                "kind": "engineering_confidence",
                "basis": (
                    "Projected area corrected using one "
                    "official mean roof slope."
                ),
            },
            "roof_type": {
                "score": roof_type_score,
                "kind": roof_type_kind,
                "basis": roof_type_basis,
            },
            "mean_roof_slope": {
                "score": (
                    1.0
                    if mean_slope_deg is not None
                    else None
                ),
                "kind": "official_source",
                "basis": (
                    "Direct matched value from Stadt Wien "
                    "Photovoltaik Potenzial 2022."
                    if mean_slope_deg is not None
                    else None
                ),
            },
            "roof_material": {
                "score": material_probability,
                "kind": (
                    "model_probability"
                    if material_probability is not None
                    else None
                ),
                "basis": (
                    "Raw classifier output; not a calibrated "
                    "statistical confidence."
                    if material_probability is not None
                    else None
                ),
            },
        },
        "score_semantics": (
            "official_source and engineering_confidence scores "
            "describe provenance/derivation reliability; "
            "model_probability values are raw neural-network "
            "outputs and are not calibrated confidence estimates."
        ),
    }


@bp.post("/select-building")
def select_building():
    """
    Save the clicked building, enrich it from official datasets, and run
    the fine-tuned rooftop classifiers on its masked roof image.

    Official-data collection and roof-AI inference run concurrently since
    they're independent (WFS calls vs. tile download + model inference),
    so the endpoint's latency is roughly the slower of the two rather than
    their sum. A roof-AI failure does not fail the whole request - see
    _run_roof_ai().
    """

    data = request.get_json(silent=True)

    if not data:
        return {
            "status": "error",
            "message": "No JSON data received.",
        }, 400

    geometry = data.get("geometry")

    if not geometry:
        return {
            "status": "error",
            "message": "No building geometry received.",
        }, 400

    address_code = data.get("address_code") or data.get(
        "official_building_id"
    )

    fmzk_data = {
        "building_key": data.get("building_key"),
        "address_code": address_code,
        "polygon_ids": data.get("polygon_ids"),
        "part_count": data.get("part_count"),
        "building_type": data.get("building_type"),
        "footprint_area_m2": data.get("footprint_area_m2"),
        "height_class": data.get("height_class"),
        "feature_class": data.get("feature_class"),
        "subclass": data.get("subclass"),
        "reference_code": data.get("reference_code"),
        "eave_elevation_m": data.get("eave_elevation_m"),
        "lower_overbuild_elevation_m": data.get(
            "lower_overbuild_elevation_m"
        ),
        "terrain_elevation_m": data.get("terrain_elevation_m"),
        "lowest_terrain_edge_m": data.get("lowest_terrain_edge_m"),
        "approx_eave_height_m": data.get("approx_eave_height_m"),
    }

    # The clicked FMZK geometry is already the spatial outline used throughout
    # the pipeline. Expose it explicitly as a plan-view roof-outline
    # approximation so it can later be written directly into roof_attributes.json.
    #
    # This is NOT an independently segmented roof boundary from the orthophoto;
    # it is the official building footprint used as a roof-plan approximation.
    roof_outline = {
        "geometry": geometry,
        "geometry_type": geometry.get("type"),
        "source": "Stadt Wien – Baukörpermodell / FMZK",
        "method": (
            "Official building footprint used as "
            "plan-view roof approximation"
        ),
        "confidence": 0.95,
        "confidence_kind": "engineering_confidence",
        "confidence_basis": (
            "High-confidence official FMZK geometry used as a "
            "plan-view roof approximation; not an image-segmentation probability."
        ),
    }

    selected_feature = {
        "type": "Feature",
        "properties": fmzk_data,
        "geometry": geometry,
    }

    selected_building_file = current_app.config["SELECTED_BUILDING_FILE"]

    with selected_building_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            selected_feature,
            file,
            indent=2,
            ensure_ascii=False,
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            official_future = executor.submit(
                collect_official_building_data,
                geometry=geometry,
                address_code=address_code,
                fmzk_data=fmzk_data,
            )
            roof_ai_future = executor.submit(_run_roof_ai)

            official = official_future.result()
            roof_ai = roof_ai_future.result()
    except Exception as error:
        return {
            "status": "error",
            "message": f"Official-data enrichment failed: {error}",
        }, 500

    roof_record = _build_roof_record(
        official=official,
        fmzk_data=fmzk_data,
        roof_outline=roof_outline,
        roof_ai=roof_ai,
    )

    print("\n" + "=" * 72)
    print("OFFICIAL BUILDING PROFILE COLLECTED")
    print("=" * 72)
    print(f"Address code:      {address_code}")
    print(f"Building key:      {fmzk_data['building_key']}")
    print(f"Polygon IDs:       {fmzk_data['polygon_ids']}")
    print(f"Building parts:    {fmzk_data['part_count']}")
    print(f"Footprint:         {fmzk_data['footprint_area_m2']} m²")
    print(f"Saved selection:   {selected_building_file}")
    print(f"Roof features AI:  {roof_ai['features'].get('status')}")
    print(f"Roof material AI:  {roof_ai['material'].get('status')}")
    print("=" * 72)

    return jsonify(
        {
            "status": "success",
            "message": "Official building data collected successfully.",
            "address_code": address_code,
            "official": official,
            "roof_outline": roof_outline,
            "roof_features_ai": roof_ai["features"],
            "roof_material_ai": roof_ai["material"],
            "roof_record": roof_record,
        }
    )


# ================================================================
# HEALTH CHECK
# ================================================================


@bp.get("/health")
def health():
    return {
        "status": "ok",
        "map_exists": current_app.config["MAP_OUTPUT_FILE"].exists(),
        "selection_exists": current_app.config["SELECTED_BUILDING_FILE"].exists(),
    }
