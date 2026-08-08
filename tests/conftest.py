import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        MAP_OUTPUT_FILE=tmp_path / "map.html",
        SELECTED_BUILDING_FILE=tmp_path / "selected_building.geojson",
    )
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
