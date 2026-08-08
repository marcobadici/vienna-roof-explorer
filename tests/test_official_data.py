import numpy as np
import pandas as pd

from app import official_data


def test_clean_scalar_handles_numpy_and_missing_values():
    assert official_data._clean_scalar(np.float64(12.34567)) == 12.346
    assert official_data._clean_scalar(np.int64(7)) == 7
    assert official_data._clean_scalar(np.nan) is None
    assert official_data._clean_scalar(" null ") is None
    assert official_data._clean_scalar("Vienna") == "Vienna"


def test_normalise_id_handles_numeric_strings():
    assert official_data._normalise_id("036454") == "36454"
    assert official_data._normalise_id("4003752460.0") == "4003752460"
    assert official_data._normalise_id("ABC-12") == "ABC-12"


def test_parse_display_address_with_district_prefix():
    street, number = official_data._parse_display_address(
        "13., Winkelbreiten 6"
    )

    assert street == "Winkelbreiten"
    assert number == "6"


def test_parse_display_address_without_house_number_returns_none():
    street, number = official_data._parse_display_address(
        "Winkelbreiten"
    )

    assert street is None
    assert number is None


def test_match_by_address_code_normalises_ids():
    frame = pd.DataFrame(
        {
            "ACD": ["100", "036454", "200"],
            "name": ["A", "Target", "B"],
        }
    )

    row = official_data._match_by_address_code(
        frame,
        "36454",
    )

    assert row is not None
    assert row["name"] == "Target"
