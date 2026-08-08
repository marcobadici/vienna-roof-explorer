from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import shape

from .config import Config


# ================================================================
# CONFIGURATION
#
# WFS_URL / WGS84 / METRIC_CRS / BEV_GPKG are aliased from the central
# Config rather than redefined here, so there is exactly one place that
# knows about coordinate systems, service URLs, and file locations across
# the whole app. Everything below this block is unchanged from before.
# ================================================================

WFS_URL = Config.WFS_URL
WGS84 = Config.WGS84
METRIC_CRS = Config.METRIC_CRS  # Vienna / UTM zone 33N

WFS_LAYERS = {
    "addresses": "ogdwien:ADRESSENOGD",
    "street_names": "ogdwien:GEONAMENSVERZOGD",
    "building_info": "ogdwien:GEBAEUDEINFOOGD",
    "building_period_detail": "ogdwien:BAUPERIODEDETAILOGD",
    "building_period_broad": "ogdwien:BAUPERIODEGROBOGD",
    "building_typology": "ogdwien:GEBAEUDETYPOGD",
    "pv_performance": "ogdwien:ANLAGENLEISTUNGOGD",
    "protection_zone": "ogdwien:SCHUTZZONEOGD",
    "zoning": "ogdwien:GENFLWIDMUNGOGD",
    "municipal_housing": "ogdwien:GEMBAUTENFLOGD",
}

REQUEST_TIMEOUT = 30
MAX_FEATURES_PER_SOURCE = 500
BBOX_PADDING_DEGREES = 0.00035  # roughly 25-40 m in Vienna

BEV_GPKG = Config.BEV_GPKG_PATH


# ================================================================
# GENERIC HELPERS
# ================================================================


def _clean_scalar(value: Any) -> Any:
    """Convert pandas/numpy scalars into JSON-safe Python values."""

    if value is None:
        return None

    if isinstance(value, (np.floating, float)):
        if np.isnan(value):
            return None
        return round(float(value), 3)

    if isinstance(value, (np.integer, int)):
        return int(value)

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null"}:
        return None

    return text


def _first_value(
    row: pd.Series | dict | None,
    *candidates: str,
) -> Any:
    """Return the first available non-empty field from a record."""

    if row is None:
        return None

    for field in candidates:
        if field in row:
            value = _clean_scalar(row[field])
            if value is not None:
                return value

    return None


def _number(
    row: pd.Series | dict | None,
    *candidates: str,
) -> float | None:
    """Return the first available field converted to float."""

    value = _first_value(row, *candidates)

    if value is None:
        return None

    try:
        return round(float(str(value).replace(",", ".")), 3)
    except (TypeError, ValueError):
        return None


def _normalise_id(value: Any) -> str | None:
    """Normalise numeric-looking identifiers for reliable comparisons."""

    value = _clean_scalar(value)

    if value is None:
        return None

    text = str(value).strip()

    try:
        numeric = float(text.replace(",", "."))
        if numeric.is_integer():
            return str(int(numeric))
    except ValueError:
        pass

    return text


def _selected_gdf(geometry: dict) -> gpd.GeoDataFrame:
    geom = shape(geometry)

    if geom.is_empty:
        raise ValueError("Selected building geometry is empty.")

    return gpd.GeoDataFrame(
        [{"geometry": geom}],
        geometry="geometry",
        crs=WGS84,
    )


def _query_bbox(selected: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    west, south, east, north = selected.total_bounds

    return (
        west - BBOX_PADDING_DEGREES,
        south - BBOX_PADDING_DEGREES,
        east + BBOX_PADDING_DEGREES,
        north + BBOX_PADDING_DEGREES,
    )


def _wfs_get(
    layer: str,
    bbox: tuple[float, float, float, float],
    count: int = MAX_FEATURES_PER_SOURCE,
) -> gpd.GeoDataFrame:
    """Query one Vienna WFS layer in a small bounding box."""

    west, south, east, north = bbox

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer,
        "outputFormat": "application/json",
        "srsName": WGS84,
        "bbox": f"{west},{south},{east},{north},{WGS84}",
        "count": count,
    }

    response = requests.get(
        WFS_URL,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    payload = response.json()
    features = payload.get("features", [])

    if not features:
        return gpd.GeoDataFrame(
            geometry=[],
            crs=WGS84,
        )

    frame = gpd.GeoDataFrame.from_features(
        features,
        crs=WGS84,
    )

    return frame[
        frame.geometry.notna()
        & ~frame.geometry.is_empty
    ].copy()


def _source_result(
    source: str,
    status: str,
    data: dict | None = None,
    message: str | None = None,
) -> dict:
    return {
        "source": source,
        "status": status,
        "message": message,
        "data": data or {},
    }


def _best_spatial_match(
    selected: gpd.GeoDataFrame,
    candidates: gpd.GeoDataFrame,
    max_point_distance_m: float = 40.0,
) -> pd.Series | None:
    """
    Pick the best record for a selected building.

    Polygon/line candidates: largest intersection with the building.
    Point candidates: nearest point to the building within a small threshold.
    """

    if candidates.empty:
        return None

    selected_metric = selected.to_crs(METRIC_CRS)
    candidates_metric = candidates.to_crs(METRIC_CRS)

    building_geometry = selected_metric.geometry.iloc[0]

    polygon_scores: list[tuple[float, int]] = []
    point_scores: list[tuple[float, int]] = []

    for index, geometry in candidates_metric.geometry.items():
        if geometry is None or geometry.is_empty:
            continue

        geom_type = geometry.geom_type

        if "Point" in geom_type:
            distance = geometry.distance(building_geometry)
            point_scores.append((distance, index))
        else:
            intersection_area = geometry.intersection(
                building_geometry
            ).area

            if intersection_area > 0:
                polygon_scores.append(
                    (intersection_area, index)
                )

    if polygon_scores:
        _, best_index = max(
            polygon_scores,
            key=lambda item: item[0],
        )
        return candidates.loc[best_index]

    if point_scores:
        distance, best_index = min(
            point_scores,
            key=lambda item: item[0],
        )

        if distance <= max_point_distance_m:
            return candidates.loc[best_index]

    return None


def _match_by_address_code(
    candidates: gpd.GeoDataFrame,
    address_code: str | None,
) -> pd.Series | None:
    if candidates.empty or not address_code:
        return None

    target = _normalise_id(address_code)

    for field in ("ACD", "BW_GEB_ID", "BEZUG"):
        if field not in candidates.columns:
            continue

        matches = candidates[
            candidates[field].apply(_normalise_id) == target
        ]

        if not matches.empty:
            return matches.iloc[0]

    return None


# Vienna's address display strings consistently read
# "<district>., <street name> <housenumber>", e.g. "13., Riedelgasse 34" -
# though some records omit the district prefix. Some ADRESSENOGD records
# carry this ready-made string in NAME_ONR/NAME/OBJEKTID_NAME_STR but leave
# the separate street-name column empty (and vice versa), so parsing it out
# is a more reliable fallback than guessing more raw column names.
_DISTRICT_PREFIX_PATTERN = re.compile(r"^\s*\d{1,2}\.,?\s*")
_TRAILING_HOUSE_NUMBER_PATTERN = re.compile(
    r"^(?P<street>.+?)\s+(?P<house_number>\d[\w./-]*)\s*$"
)


def _parse_display_address(
    display: str | None,
) -> tuple[str | None, str | None]:
    """Best-effort split of a "[district.,] street housenumber" string."""

    if not display:
        return None, None

    remainder = _DISTRICT_PREFIX_PATTERN.sub("", display, count=1)
    match = _TRAILING_HOUSE_NUMBER_PATTERN.match(remainder)

    if not match:
        return None, None

    return match.group("street"), match.group("house_number")


def _looks_like_street_name(value: str | None) -> bool:
    """
    Reject values that are actually a numeric street code (e.g. "04025"),
    not a real street name. One of the guessed raw field names turned out
    to be a street-code column rather than street-name text on some
    ADRESSENOGD records, so this guards against silently trusting it - a
    genuine street name always contains at least one letter.
    """

    return bool(value) and any(char.isalpha() for char in value)


def _raw_street_field(row: pd.Series) -> str | None:
    """The raw value from whichever guessed street column exists, unvalidated."""

    return _first_value(
        row,
        "STR_NAME",
        "SCD_NAME_STR",
        "TOPOGR_NAME_STR",
        "STRNAML",
        "STRASSE",
    )


def _collect_street_codes(frame: gpd.GeoDataFrame) -> set[str]:
    """Gather every raw street-field value in frame that looks like a code."""

    if frame.empty:
        return set()

    raw_values = frame.apply(_raw_street_field, axis=1)

    return {
        value
        for value in raw_values
        if value and not _looks_like_street_name(value)
    }


def _lookup_street_names(codes: set[str]) -> dict[str, str]:
    """
    Resolve Vienna street codes (SCD) to their official street names via
    the city's street-names register (Straßenverzeichnis), so a numeric
    code found on an address record can be converted to real text instead
    of being discarded.
    """

    codes = {code for code in codes if code}

    if not codes:
        return {}

    quoted_codes = ",".join(f"'{code}'" for code in sorted(codes))

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYERS["street_names"],
        "outputFormat": "application/json",
        "cql_filter": f"SCD IN ({quoted_codes})",
        "count": len(codes),
    }

    try:
        response = requests.get(
            WFS_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {}

    mapping: dict[str, str] = {}

    for feature in payload.get("features", []):
        properties = feature.get("properties", {}) or {}
        code = _clean_scalar(properties.get("SCD"))
        name = _clean_scalar(properties.get("STR_NAME"))

        if code and name:
            mapping[code] = name

    return mapping


def _extract_address_fields(
    row: pd.Series,
    street_lookup: dict[str, str] | None = None,
) -> dict:
    """Pull address, street, and house number out of one ADRESSENOGD row."""

    street = _raw_street_field(row)

    if not _looks_like_street_name(street):
        # The raw value is a numeric street code rather than text - resolve
        # it against the street-names register if we have a lookup for it,
        # otherwise drop it so the display-string fallback below can try.
        street = (street_lookup or {}).get(street) if street else None

    house_number = _first_value(
        row,
        "ONR_VON",
        "ONR",
    )

    address = _first_value(
        row,
        "NAME_ONR",
        "NAME",
        "OBJEKTID_NAME_STR",
    )

    parsed_street, parsed_house_number = _parse_display_address(address)

    street = street or parsed_street
    house_number = house_number or parsed_house_number

    # Prefer a clean "street housenumber" string over the raw display value,
    # which sometimes carries a leading "13., " district prefix - district
    # is already shown as its own field, so it shouldn't clutter the address.
    if street and house_number:
        address = f"{street} {house_number}"
    elif street:
        address = street
    elif house_number:
        address = house_number
    # else: keep whatever raw display string we found (may be None), since
    # it's better than nothing when neither part could be isolated.

    return {
        "address": address,
        "street": street,
        "house_number": house_number,
    }


def _nearby_address_records(
    selected: gpd.GeoDataFrame,
    candidates: gpd.GeoDataFrame,
    buffer_m: float = 15.0,
    street_lookup: dict[str, str] | None = None,
) -> list[dict]:
    """
    Return every distinct address record within buffer_m of the building,
    closest first, each already run through _extract_address_fields.

    Many Vienna buildings - corner buildings, larger housing complexes -
    have more than one official entrance address, so relying on a single
    nearest-point match can silently drop legitimate addresses. Sorting by
    distance also lets callers upgrade a low-quality match (e.g. one with
    a house number but no street) to a nearby record that has full data.
    """

    if candidates.empty:
        return []

    selected_metric = selected.to_crs(METRIC_CRS)
    candidates_metric = candidates.to_crs(METRIC_CRS)

    building_geometry = selected_metric.geometry.iloc[0]

    scored: list[tuple[float, int]] = []

    for index, geometry in candidates_metric.geometry.items():
        if geometry is None or geometry.is_empty:
            continue

        distance = geometry.distance(building_geometry)

        if distance <= buffer_m:
            scored.append((distance, index))

    scored.sort(key=lambda item: item[0])

    seen: set[str] = set()
    records: list[dict] = []

    for _distance, index in scored:
        fields = _extract_address_fields(
            candidates.loc[index],
            street_lookup=street_lookup,
        )

        if not fields["address"] or fields["address"] in seen:
            continue

        seen.add(fields["address"])
        records.append(fields)

    return records


def _query_source(
    selected: gpd.GeoDataFrame,
    key: str,
) -> tuple[gpd.GeoDataFrame | None, str | None]:
    try:
        return _wfs_get(
            WFS_LAYERS[key],
            _query_bbox(selected),
        ), None
    except (requests.RequestException, ValueError) as error:
        return None, str(error)


# ================================================================
# VIENNA OFFICIAL DATA SOURCES
# ================================================================


def _address_data(
    selected: gpd.GeoDataFrame,
    address_code: str | None,
) -> dict:
    frame, error = _query_source(selected, "addresses")

    if error:
        return _source_result(
            "Stadt Wien – Adressen Standorte Wien",
            "error",
            message=error,
        )

    row = _match_by_address_code(frame, address_code)

    if row is None:
        row = _best_spatial_match(selected, frame)

    # Resolve any numeric street codes found in this response to real
    # street names in one batched lookup, rather than per-record.
    street_lookup = _lookup_street_names(_collect_street_codes(frame))

    nearby_records = _nearby_address_records(
        selected,
        frame,
        street_lookup=street_lookup,
    )
    all_addresses = sorted(
        {record["address"] for record in nearby_records if record["address"]}
    )

    if row is None:
        if nearby_records:
            # Prefer the nearest record that actually has a street name
            # over the plain-nearest one, which may be missing it.
            best = next(
                (record for record in nearby_records if record["street"]),
                nearby_records[0],
            )

            return _source_result(
                "Stadt Wien – Adressen Standorte Wien",
                "matched",
                {
                    "address": best["address"],
                    "addresses": all_addresses,
                    "street": best["street"],
                    "house_number": best["house_number"],
                },
            )

        return _source_result(
            "Stadt Wien – Adressen Standorte Wien",
            "no_match",
        )

    fields = _extract_address_fields(row, street_lookup=street_lookup)

    if not fields["street"]:
        # The confirmed match (by ID) has a house number but no street -
        # a nearby record for the same building usually has the full
        # picture, so prefer that one for display purposes.
        better = next(
            (record for record in nearby_records if record["street"]),
            None,
        )

        if better:
            fields = better

    street = fields["street"]
    house_number = fields["house_number"]
    address = fields["address"]

    # Make sure the confirmed match is always included in the full list,
    # even if it happened to fall just outside the nearby-address buffer.
    if address and address not in all_addresses:
        all_addresses = sorted(all_addresses + [address])

    return _source_result(
        "Stadt Wien – Adressen Standorte Wien",
        "matched",
        {
            "address": address,
            "addresses": all_addresses,
            "street": street,
            "house_number": house_number,
            "postal_code": _first_value(row, "PLZ"),
            "district": _first_value(
                row,
                "GEB_BEZIRK",
                "BEZ",
                "BEZIRK",
            ),
            "address_code": _first_value(
                row,
                "ACD",
            ) or address_code,
            "building_object_id": _first_value(
                row,
                "GEB_OBJEKTID",
            ),
            "building_status": _first_value(
                row,
                "GEB_STATUS_KURZTEXT",
                "GEB_STATUS",
            ),
            "building_block": _first_value(
                row,
                "GEB_BAUBLOCK",
                "GEB_BAUBLOCK_ID",
            ),
        },
    )


def _building_history_data(
    selected: gpd.GeoDataFrame,
    address_code: str | None,
) -> dict:
    frame, error = _query_source(selected, "building_info")

    if error:
        return _source_result(
            "Stadt Wien – Gebäudeinformation",
            "error",
            message=error,
        )

    row = _match_by_address_code(frame, address_code)

    if row is None:
        row = _best_spatial_match(selected, frame)

    if row is None:
        return _source_result(
            "Stadt Wien – Gebäudeinformation",
            "no_match",
        )

    return _source_result(
        "Stadt Wien – Gebäudeinformation",
        "matched",
        {
            "construction_year": _first_value(
                row,
                "BAUJAHR",
            ),
            "architect": _first_value(
                row,
                "ARCHITEKT",
            ),
            "complex_name": _first_value(
                row,
                "HA_NAME",
            ),
            "street": _first_value(
                row,
                "STRNAML",
            ),
            "district": _first_value(
                row,
                "BEZ",
            ),
            "address_code": _first_value(
                row,
                "ACD",
            ) or address_code,
        },
    )


def _period_typology_data(
    selected: gpd.GeoDataFrame,
    address_code: str | None,
) -> dict:
    detail_frame, detail_error = _query_source(
        selected,
        "building_period_detail",
    )

    broad_frame, broad_error = _query_source(
        selected,
        "building_period_broad",
    )

    typology_frame, typology_error = _query_source(
        selected,
        "building_typology",
    )

    def matched_row(frame: gpd.GeoDataFrame | None) -> pd.Series | None:
        if frame is None or frame.empty:
            return None

        row = _match_by_address_code(
            frame,
            address_code,
        )

        if row is None:
            row = _best_spatial_match(
                selected,
                frame,
            )

        return row

    detail_row = matched_row(detail_frame)
    broad_row = matched_row(broad_frame)
    typology_row = matched_row(typology_frame)

    if (
        detail_row is None
        and broad_row is None
        and typology_row is None
    ):
        errors = [
            error
            for error in (
                detail_error,
                broad_error,
                typology_error,
            )
            if error
        ]

        return _source_result(
            "Stadt Wien – Bauperioden und Bautypologien",
            "error" if errors else "no_match",
            message=" | ".join(errors) or None,
        )

    return _source_result(
        "Stadt Wien – Bauperioden und Bautypologien",
        "matched",
        {
            "period_detail_code": _first_value(
                detail_row,
                "OBJ_STR",
            ),
            "period_detail": _first_value(
                detail_row,
                "OBJ_STR_TXT",
            ),
            "period_broad_code": _first_value(
                broad_row,
                "OBJ_STR2",
                "OBJ_STR",
            ) or _first_value(
                detail_row,
                "OBJ_STR2",
            ),
            "period_broad": _first_value(
                broad_row,
                "OBJ_STR2_TXT",
                "OBJ_STR_TXT",
            ) or _first_value(
                detail_row,
                "OBJ_STR2_TXT",
            ),
            "typology_code": _first_value(
                typology_row,
                "BAUTYP",
            ) or _first_value(
                detail_row,
                "BAUTYP",
            ),
            "typology": _first_value(
                typology_row,
                "BAUTYP_TXT",
            ) or _first_value(
                detail_row,
                "BAUTYP_TXT",
            ),
            "address_code": _first_value(
                detail_row,
                "ACD",
            ) or _first_value(
                broad_row,
                "ACD",
            ) or _first_value(
                typology_row,
                "ACD",
            ) or address_code,
        },
    )


def _pv_data(selected: gpd.GeoDataFrame) -> dict:
    frame, error = _query_source(selected, "pv_performance")

    if error:
        return _source_result(
            "Stadt Wien – Photovoltaik Potenzial 2022",
            "error",
            message=error,
        )

    row = _best_spatial_match(selected, frame)

    if row is None:
        return _source_result(
            "Stadt Wien – Photovoltaik Potenzial 2022",
            "no_match",
        )

    return _source_result(
        "Stadt Wien – Photovoltaik Potenzial 2022",
        "matched",
        {
            "address": _first_value(row, "ADRESSE"),
            "district": _first_value(row, "BEZ", "BEZIRK"),
            "annual_yield_kwh_m2a": _number(row, "YR"),
            "mean_roof_slope_deg": _number(row, "SLOPE_MEAN"),
            "roof_type": _first_value(row, "DACHTYP"),
            "pv_area_medium_m2": _number(row, "MITTEL"),
            "pv_area_good_m2": _number(row, "GUT"),
            "pv_area_very_good_m2": _number(
                row,
                "SEHRGUT",
            ),
            "theoretical_pv_capacity_kwp": _number(
                row,
                "ANLAGENLEISTUNG",
            ),
            "monument_protection_2020": _first_value(
                row,
                "DENKMALSCHUTZ",
            ),
        },
    )


def _protection_zone_data(selected: gpd.GeoDataFrame) -> dict:
    frame, error = _query_source(selected, "protection_zone")

    if error:
        return _source_result(
            "Stadt Wien – Schutzzonen",
            "error",
            message=error,
        )

    row = _best_spatial_match(selected, frame)

    if row is None:
        return _source_result(
            "Stadt Wien – Schutzzonen",
            "matched",
            {
                "in_protection_zone": False,
                "zone_name": None,
            },
        )

    return _source_result(
        "Stadt Wien – Schutzzonen",
        "matched",
        {
            "in_protection_zone": True,
            "zone_name": _first_value(
                row,
                "SKURZ",
                "BEZEICHNUNG",
                "NAME",
                "KURZBEZ",
                "TEXT",
                "SCHUTZZONE",
            ),
        },
    )


def _zoning_data(selected: gpd.GeoDataFrame) -> dict:
    frame, error = _query_source(selected, "zoning")

    if error:
        return _source_result(
            "Stadt Wien – Generalisierte Flächenwidmung",
            "error",
            message=error,
        )

    row = _best_spatial_match(selected, frame)

    if row is None:
        return _source_result(
            "Stadt Wien – Generalisierte Flächenwidmung",
            "no_match",
        )

    return _source_result(
        "Stadt Wien – Generalisierte Flächenwidmung",
        "matched",
        {
            "zoning_class": _first_value(
                row,
                "WIDMUNGSKLASSE",
            ),
            "zoning": _first_value(
                row,
                "WIDMUNG",
            ),
            "zoning_detail": _first_value(
                row,
                "WIDMUNG_DETAIL",
            ),
            "shopping_centre": _first_value(row, "EKZ"),
            "public_purpose": _first_value(row, "OEZ"),
            "structure": _first_value(row, "STR"),
            "structure_unit": _first_value(row, "STRE"),
            "structure_area": _first_value(row, "STRG"),
            "temporary_plan_document": _first_value(
                row,
                "BEFRISTUNG_PD",
            ),
            "temporary_until": _first_value(
                row,
                "BEFRISTUNG_DATUM",
            ),
            "district": _first_value(row, "BEZIRK"),
        },
    )


def _municipal_housing_data(selected: gpd.GeoDataFrame) -> dict:
    frame, error = _query_source(selected, "municipal_housing")

    if error:
        return _source_result(
            "Stadt Wien / Wiener Wohnen – Gemeindebauten",
            "error",
            message=error,
        )

    row = _best_spatial_match(selected, frame)

    if row is None:
        return _source_result(
            "Stadt Wien / Wiener Wohnen – Gemeindebauten",
            "matched",
            {
                "municipal_housing": False,
            },
        )

    return _source_result(
        "Stadt Wien / Wiener Wohnen – Gemeindebauten",
        "matched",
        {
            "municipal_housing": True,
            "estate_name": _first_value(row, "HOFNAME"),
            "number_of_dwellings": _first_value(
                row,
                "WOHNUNGSANZAHL",
            ),
            "construction_year": _first_value(
                row,
                "BAUJAHR",
            ),
            "address": _first_value(row, "ADRESSE"),
            "district": _first_value(row, "BEZIRK"),
            "information_link": _first_value(
                row,
                "WEBLINK1",
            ),
        },
    )


# ================================================================
# OPTIONAL LOCAL BEV DLM BAUWERKE ENRICHMENT
# ================================================================


@lru_cache(maxsize=1)
def _load_bev() -> gpd.GeoDataFrame | None:
    if not BEV_GPKG.exists():
        return None

    frame = gpd.read_file(BEV_GPKG)

    if frame.empty:
        return None

    if frame.crs is None:
        raise ValueError(
            "BEV GeoPackage has no CRS. Please define the source CRS."
        )

    return frame


def _bev_data(selected: gpd.GeoDataFrame) -> dict:
    try:
        frame = _load_bev()
    except Exception as error:
        return _source_result(
            "BEV – DLM Bauwerke",
            "error",
            message=str(error),
        )

    if frame is None:
        return _source_result(
            "BEV – DLM Bauwerke",
            "not_configured",
            message=(
                "Optional local BEV GeoPackage not found at "
                f"{BEV_GPKG}."
            ),
        )

    selected_in_bev = selected.to_crs(frame.crs)
    west, south, east, north = selected_in_bev.total_bounds

    subset = frame.cx[west:east, south:north].copy()

    if subset.empty:
        return _source_result(
            "BEV – DLM Bauwerke",
            "no_match",
        )

    subset_wgs = subset.to_crs(WGS84)
    row = _best_spatial_match(selected, subset_wgs)

    if row is None:
        return _source_result(
            "BEV – DLM Bauwerke",
            "no_match",
        )

    # BEV field names can differ between product versions/export schemas.
    # The aliases below deliberately cover common variants; unknown columns
    # simply remain null and can be extended after inspecting the downloaded
    # GeoPackage once.
    return _source_result(
        "BEV – DLM Bauwerke",
        "matched",
        {
            "ground_elevation_m": _number(
                row,
                "BODENHOEHE",
                "BODENHOEHE_M",
                "BODENH",
                "HOEHE_BODEN",
            ),
            "mean_object_height_m": _number(
                row,
                "MITTLERE_OBJEKTHOEHE",
                "MITTL_OBJEKTHOEHE",
                "OBJHOEHE_MITTEL",
                "HOEHE_MITTEL",
            ),
            "maximum_object_height_m": _number(
                row,
                "MAXIMALE_OBJEKTHOEHE",
                "MAX_OBJEKTHOEHE",
                "OBJHOEHE_MAX",
                "HOEHE_MAX",
            ),
            "agwr_object_number": _first_value(
                row,
                "AGWR_OBJEKTNUMMER",
                "AGWR_OBJ_NR",
                "AGWR",
            ),
        },
    )


# ================================================================
# PUBLIC ENTRY POINT
# ================================================================


def collect_official_building_data(
    geometry: dict,
    address_code: str | None,
    fmzk_data: dict | None = None,
) -> dict:
    """Collect official information for one clicked Vienna building."""

    selected = _selected_gdf(geometry)

    sources = {
        "fmzk": _source_result(
            "Stadt Wien – Baukörpermodell / FMZK",
            "matched",
            fmzk_data or {},
        )
    }

    jobs = {
        "address": (
            "Stadt Wien – Adressen Standorte Wien",
            lambda: _address_data(selected, address_code),
        ),
        "building_history": (
            "Stadt Wien – Gebäudeinformation",
            lambda: _building_history_data(selected, address_code),
        ),
        "period_typology": (
            "Stadt Wien – Bauperioden und Bautypologien",
            lambda: _period_typology_data(selected, address_code),
        ),
        "pv": (
            "Stadt Wien – Photovoltaik Potenzial 2022",
            lambda: _pv_data(selected),
        ),
        "protection_zone": (
            "Stadt Wien – Schutzzonen",
            lambda: _protection_zone_data(selected),
        ),
        "zoning": (
            "Stadt Wien – Generalisierte Flächenwidmung",
            lambda: _zoning_data(selected),
        ),
        "municipal_housing": (
            "Stadt Wien / Wiener Wohnen – Gemeindebauten",
            lambda: _municipal_housing_data(selected),
        ),
        "bev": (
            "BEV – DLM Bauwerke",
            lambda: _bev_data(selected),
        ),
    }

    # These are independent lookups over a tiny area around one clicked
    # building. Run a few in parallel so the interactive popup does not wait
    # for eight network round trips one after another.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(function): (key, source_name)
            for key, (source_name, function) in jobs.items()
        }

        for future in as_completed(futures):
            key, source_name = futures[future]

            try:
                sources[key] = future.result()
            except Exception as error:
                sources[key] = _source_result(
                    source_name,
                    "error",
                    message=str(error),
                )

    # ------------------------------------------------------------
    # Flatten the most useful values for the frontend.
    # Source objects remain present so provenance is never lost.
    # ------------------------------------------------------------

    def data(source_key: str) -> dict:
        return sources[source_key].get("data", {})

    address = data("address")
    history = data("building_history")
    period = data("period_typology")
    pv = data("pv")
    protection = data("protection_zone")
    zoning = data("zoning")
    municipal = data("municipal_housing")
    bev = data("bev")

    profile = {
        "identification": {
            "address": address.get("address")
            or pv.get("address")
            or municipal.get("address"),
            "addresses": address.get("addresses") or [],
            "street": address.get("street"),
            "postal_code": address.get("postal_code"),
            "district": address.get("district")
            or history.get("district")
            or pv.get("district"),
            "address_code": address.get("address_code")
            or history.get("address_code")
            or address_code,
            "building_object_id": address.get("building_object_id"),
            "building_status": address.get("building_status"),
            "building_block": address.get("building_block"),
        },
        "geometry_elevation": {
            **(fmzk_data or {}),
            "bev_ground_elevation_m": bev.get("ground_elevation_m"),
            "bev_mean_height_m": bev.get("mean_object_height_m"),
            "bev_max_height_m": bev.get("maximum_object_height_m"),
            "agwr_object_number": bev.get("agwr_object_number"),
        },
        "history_typology": {
            "construction_year": history.get("construction_year")
            or municipal.get("construction_year"),
            "architect": history.get("architect"),
            "complex_name": history.get("complex_name")
            or municipal.get("estate_name"),
            "construction_period_detail": period.get("period_detail"),
            "construction_period_broad": period.get("period_broad"),
            "typology": period.get("typology"),
            "typology_code": period.get("typology_code"),
        },
        "roof_solar": {
            "roof_type": pv.get("roof_type"),
            "mean_roof_slope_deg": pv.get("mean_roof_slope_deg"),
            "annual_yield_kwh_m2a": pv.get("annual_yield_kwh_m2a"),
            "pv_area_medium_m2": pv.get("pv_area_medium_m2"),
            "pv_area_good_m2": pv.get("pv_area_good_m2"),
            "pv_area_very_good_m2": pv.get("pv_area_very_good_m2"),
            "theoretical_pv_capacity_kwp": pv.get(
                "theoretical_pv_capacity_kwp"
            ),
        },
        "planning_status": {
            "in_protection_zone": protection.get("in_protection_zone"),
            "protection_zone_name": protection.get("zone_name"),
            "monument_protection_2020": pv.get(
                "monument_protection_2020"
            ),
            "zoning_class": zoning.get("zoning_class"),
            "zoning": zoning.get("zoning"),
            "zoning_detail": zoning.get("zoning_detail"),
            "temporary_plan_document": zoning.get(
                "temporary_plan_document"
            ),
            "temporary_until": zoning.get("temporary_until"),
            "municipal_housing": municipal.get("municipal_housing"),
            "municipal_estate_name": municipal.get("estate_name"),
            "municipal_dwellings": municipal.get("number_of_dwellings"),
            "municipal_information_link": municipal.get(
                "information_link"
            ),
        },
    }

    return {
        "profile": profile,
        "sources": sources,
    }
