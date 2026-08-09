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
        geometry=[box(i, 0, i + 1, 1) for i in range(4)],
        crs="EPSG:3857",
    )
    area = StudyArea(
        slug="test",
        name="Test",
        center_lat=0.5,
        center_lon=0.5,
        polygon_lon_lat=((0, 0), (4, 0), (4, 1), (0, 1)),
        anchors_lon_lat=(("West", 0.5, 0.5), ("East", 3.5, 0.5)),
    )
    result, rankings, summary = build_neighborhood_similarity(cells, area)
    assert len(rankings) == 8
    assert summary["anchor_count"] == 2
    assert np.isfinite(result["similarity_west"]).all()
    assert result["similarity_west"].between(0, 100).all()
