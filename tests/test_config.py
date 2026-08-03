import pytest
from shapely.geometry import Point

from dhakagraph.config import (
    AIRPORT_UTTARA_MIRPUR_SAYEDABAD,
    CENTRAL_DHAKA_PILOT,
    StudyArea,
)


def test_default_pilot_is_valid() -> None:
    assert CENTRAL_DHAKA_PILOT.center == (23.7386, 90.3954)
    assert CENTRAL_DHAKA_PILOT.radius_m == 2_500


def test_radius_must_be_positive() -> None:
    with pytest.raises(ValueError, match="radius_m"):
        StudyArea("invalid", "Invalid", 23.7, 90.4, 0)


def test_expanded_area_contains_requested_anchors() -> None:
    geometry = AIRPORT_UTTARA_MIRPUR_SAYEDABAD.geometry
    assert geometry is not None
    anchors = AIRPORT_UTTARA_MIRPUR_SAYEDABAD.anchors_lon_lat
    assert {label for label, _, _ in anchors} == {"Airport", "Uttara", "Mirpur", "Sayedabad"}
    assert all(geometry.covers(Point(lon, lat)) for _, lon, lat in anchors)


def test_study_area_requires_exactly_one_selection_method() -> None:
    with pytest.raises(ValueError, match="either radius_m or polygon_lon_lat"):
        StudyArea("invalid", "Invalid", 23.7, 90.4)
    with pytest.raises(ValueError, match="mutually exclusive"):
        StudyArea(
            "invalid",
            "Invalid",
            23.7,
            90.4,
            radius_m=1_000,
            polygon_lon_lat=((90.3, 23.6), (90.5, 23.6), (90.4, 23.8)),
        )
