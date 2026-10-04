import pytest

from trip_advisor.pipeline.structure.validate import normalize_route


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lagos\u2013Abeokuta Expressway", "Lagos-Abeokuta Expressway"),  # en dash
        ("Lagos\u2014Abeokuta Expressway", "Lagos-Abeokuta Expressway"),  # em dash
        ("Lagos-Ibadan expressway", "Lagos-Ibadan Expressway"),
        ("lagos-ibadan expressway", "Lagos-Ibadan Expressway"),
        ("Lagos - Ibadan Expressway", "Lagos-Ibadan Expressway"),
        ("Lagos-Ibadan Expressway (Kara Bridge)", "Lagos-Ibadan Expressway"),
        ("  Lagos-Ore-Benin   expressway ", "Lagos-Ore-Benin Expressway"),
        ("F209 Ore - Ondo", "F209 Ore-Ondo"),
    ],
)
def test_normalize_route(raw, expected):
    assert normalize_route(raw) == expected


def test_all_spellings_of_one_road_collapse_to_one():
    spellings = [
        "Lagos-Ibadan Expressway", "Lagos-Ibadan expressway", "Lagos\u2013Ibadan Expressway",
        "Lagos-Ibadan Expressway (Kara Bridge)",
    ]  # fmt: skip
    assert len({normalize_route(s) for s in spellings}) == 1
