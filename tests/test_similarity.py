"""Tests for neighborhood similarity analysis."""

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from dhakagraph.config import StudyArea
from dhakagraph.similarity import build_neighborhood_similarity


def test_similarity_scores_are_bounded_and_rankings_are_created() -> None:
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["a", "b", "c", "d"],
            "building_footprint_share": [0.1, 0.2, 0.8, 0.9],
            "road_density_km_km2": [1.0, 1.2, 4.0, 4.2],
            "poi_density_km2": [2.0, 2.2, 8.0, 8.2],
            "service_desert_score": [80.0, 78.0, 20.0, 18.0],
        },
        geometry=[box(90 + i * 0.01, 23, 90 + (i + 1) * 0.01, 23.01) for i in range(4)],
        crs="EPSG:4326",
    )
    area = StudyArea(
        slug="test",
        name="Test",
        center_lat=23.005,
        center_lon=90.02,
        polygon_lon_lat=((90, 23), (90.04, 23), (90.04, 23.01), (90, 23.01)),
        anchors_lon_lat=(("West", 90.005, 23.005), ("East", 90.035, 23.005)),
    )
    result, rankings, summary = build_neighborhood_similarity(cells, area)
    assert len(rankings) == 8
    assert summary["anchor_count"] == 2
    assert np.isfinite(result["similarity_west"]).all()
    assert result["similarity_west"].between(0, 100).all()
