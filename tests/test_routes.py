import json
import math

import pytest

from app import routes


SIMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [16.2830, 48.1640],
        [16.2832, 48.1640],
        [16.2832, 48.1642],
        [16.2830, 48.1642],
        [16.2830, 48.1640],
    ]],
}


def _official_profile(
    *,
    roof_type=None,
    slope=42.8,
    footprint=273.0,
    building_id="25624920",
):
    return {
        "profile": {
            "identification": {
                "address": "Winkelbreiten 6",
                "address_code": "036454",
                "building_object_id": building_id,
            },
            "geometry_elevation": {
                "footprint_area_m2": footprint,
            },
            "roof_solar": {
                "roof_type": roof_type,
                "mean_roof_slope_deg": slope,
                "annual_yield_kwh_m2a": 1237,
                "pv_area_medium_m2": 18.0,
                "pv_area_good_m2": 17.0,
                "pv_area_very_good_m2": 89.0,
                "theoretical_pv_capacity_kwp": 7.0,
            },
        },
        "sources": {},
    }


def _roof_ai():
    return {
        "features": {
            "status": "success",
            "predictions": {
                "chimney": {
                    "label": "Chimney",
                    "detected": True,
                    "probability": 0.73,
                },
                "solar": {
                    "label": "Solar panels",
                    "detected": False,
                    "probability": 0.12,
                },
            },
        },
        "material": {
            "status": "success",
            "material": "tile",
            "confidence": 0.94,
        },
    }


def _roof_outline():
    return {
        "geometry": SIMPLE_POLYGON,
        "method": "Official building footprint used as plan-view roof approximation",
        "confidence": 0.95,
        "confidence_kind": "engineering",
        "confidence_basis": "FMZK footprint proxy.",
    }


def test_clean_identifier_normalises_numeric_ids():
    assert routes.clean_identifier("036454") == "36454"
    assert routes.clean_identifier(4003752460.0) == "4003752460"
    assert routes.clean_identifier(None) is None


def test_group_building_parts_merges_parts():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "BW_GEB_ID": "36454",
                    "FMZK_ID": "1",
                    "LAYER": "building",
                    "O_KOTE": 80.0,
                    "HOEHE_DGM": 70.0,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [16.2830, 48.1640],
                        [16.2831, 48.1640],
                        [16.2831, 48.1641],
                        [16.2830, 48.1641],
                        [16.2830, 48.1640],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "BW_GEB_ID": "36454",
                    "FMZK_ID": "2",
                    "LAYER": "building",
                    "O_KOTE": 82.0,
                    "HOEHE_DGM": 70.0,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [16.2831, 48.1640],
                        [16.2832, 48.1640],
                        [16.2832, 48.1641],
                        [16.2831, 48.1641],
                        [16.2831, 48.1640],
                    ]],
                },
            },
        ],
    }

    result = routes.group_building_parts(
        payload,
        wgs84="EPSG:4326",
        metric_crs="EPSG:32633",
    )

    assert len(result["features"]) == 1
    props = result["features"][0]["properties"]
    assert props["building_key"] == "BW_36454"
    assert props["part_count"] == 2
    assert props["polygon_id"] == "1, 2"
    assert props["approx_eave_height_m"] == pytest.approx(12.0)
    assert props["footprint_area_m2"] > 0


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?west=16.28&south=48.16&east=16.27&north=48.17",
        "?west=16.0&south=48.0&east=16.2&north=48.2",
    ],
)
def test_buildings_endpoint_rejects_bad_bounds(client, query):
    response = client.get(f"/api/buildings{query}")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_health_endpoint_reports_runtime_files(client, app):
    response = client.get("/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {
        "status": "ok",
        "map_exists": False,
        "selection_exists": False,
    }

    app.config["MAP_OUTPUT_FILE"].write_text("map", encoding="utf-8")
    app.config["SELECTED_BUILDING_FILE"].write_text("{}", encoding="utf-8")

    payload = client.get("/health").get_json()
    assert payload["map_exists"] is True
    assert payload["selection_exists"] is True


def test_roof_record_derives_type_area_and_positive_features_only():
    record = routes._build_roof_record(
        official=_official_profile(),
        fmzk_data={"address_code": "036454"},
        roof_outline=_roof_outline(),
        roof_ai=_roof_ai(),
    )

    assert record["building_id"] == "25624920"
    assert record["address"] == "Winkelbreiten 6"

    roof = record["roof"]
    assert roof["type"] == "Pitched"
    assert roof["projected_area_m2"] == pytest.approx(273.0)

    expected_surface = 273.0 / math.cos(math.radians(42.8))
    assert roof["estimated_surface_area_m2"] == pytest.approx(
        round(expected_surface, 1)
    )

    assert roof["material"] == "tile"
    assert set(record["rooftop_features"]) == {"chimney"}
    assert record["rooftop_features"]["chimney"]["model_probability"] == 0.73

    assert record["confidence"]["roof_type"]["score"] == 0.95
    assert record["confidence"]["estimated_surface_area"]["score"] == 0.75
    assert record["confidence"]["roof_material"]["score"] == 0.94


def test_official_roof_type_is_not_overwritten_by_slope_rule():
    record = routes._build_roof_record(
        official=_official_profile(roof_type="Hipped", slope=3.0),
        fmzk_data={},
        roof_outline=_roof_outline(),
        roof_ai=_roof_ai(),
    )

    assert record["roof"]["type"] == "Hipped"
    assert record["confidence"]["roof_type"]["score"] == 1.0
    assert record["confidence"]["roof_type"]["kind"] == "official_source"


def test_missing_roof_data_stays_null_in_record():
    official = _official_profile(
        roof_type=None,
        slope=None,
        footprint=None,
        building_id=None,
    )
    official["profile"]["geometry_elevation"] = {}

    record = routes._build_roof_record(
        official=official,
        fmzk_data={"building_key": "BW_36454"},
        roof_outline=_roof_outline(),
        roof_ai={
            "features": {"status": "error"},
            "material": {"status": "error"},
        },
    )

    assert record["building_id"] == "BW_36454"
    assert record["roof"]["type"] is None
    assert record["roof"]["projected_area_m2"] is None
    assert record["roof"]["estimated_surface_area_m2"] is None
    assert record["roof"]["material"] is None
    assert record["rooftop_features"] == {}


def test_select_building_uses_mocked_external_processing(
    client,
    app,
    monkeypatch,
):
    official = _official_profile()
    roof_ai = _roof_ai()

    monkeypatch.setattr(
        routes,
        "collect_official_building_data",
        lambda **kwargs: official,
    )
    monkeypatch.setattr(
        routes,
        "_run_roof_ai",
        lambda: roof_ai,
    )

    response = client.post(
        "/select-building",
        json={
            "building_key": "BW_36454",
            "address_code": "036454",
            "polygon_ids": "1, 2, 3",
            "part_count": 3,
            "building_type": "building",
            "footprint_area_m2": 273.0,
            "geometry": SIMPLE_POLYGON,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["status"] == "success"
    assert payload["roof_record"]["roof"]["type"] == "Pitched"
    assert payload["roof_record"]["roof"]["material"] == "tile"
    assert app.config["SELECTED_BUILDING_FILE"].exists()

    saved = json.loads(
        app.config["SELECTED_BUILDING_FILE"].read_text(encoding="utf-8")
    )
    assert saved["type"] == "Feature"
    assert saved["geometry"] == SIMPLE_POLYGON
    assert saved["properties"]["building_key"] == "BW_36454"


def test_select_building_requires_geometry(client):
    response = client.post(
        "/select-building",
        json={"building_key": "BW_36454"},
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "No building geometry received."
