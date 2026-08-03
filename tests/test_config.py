import pytest

from dhakagraph.config import CENTRAL_DHAKA_PILOT, StudyArea


def test_default_pilot_is_valid() -> None:
    assert CENTRAL_DHAKA_PILOT.center == (23.7386, 90.3954)
    assert CENTRAL_DHAKA_PILOT.radius_m == 2_500


def test_radius_must_be_positive() -> None:
    with pytest.raises(ValueError, match="radius_m"):
        StudyArea("invalid", "Invalid", 23.7, 90.4, 0)
