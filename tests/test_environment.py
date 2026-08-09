"""Tests for environmental screening."""

import geopandas as gpd
from shapely.geometry import box

from dhakagraph.environment import build_environmental_screen


def test_environment_scores_are_bounded() -> None:
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["a", "b", "c"],
            "building_footprint_share": [0.8, 0.3, 0.1],
            "road_density_km_km2": [5, 2, 1],
            "building_density_km2": [100, 20, 5],
            "landuse_industrial_share": [0.5, 0.1, 0.0],
            "landuse_green_share": [0.0, 0.2, 0.8],
            "distance_park_m": [1000, 300, 50],
        },
        geometry=[
            box(90, 23, 90.01, 23.01),
            box(90.01, 23, 90.02, 23.01),
            box(90.02, 23, 90.03, 23.01),
        ],
        crs="EPSG:4326",
    )
    result, rankings, summary = build_environmental_screen(cells)
    assert summary["air_source"].startswith("Modeled")
    assert rankings
    for column in (
        "heat_exposure_score",
        "air_exposure_score",
        "green_deficit_score",
        "environmental_burden_score",
    ):
        assert result[column].between(0, 100).all()
