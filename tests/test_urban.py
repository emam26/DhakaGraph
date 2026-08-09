"""Tests for the cell-based urban-function analysis."""

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, box

from dhakagraph.accessibility import build_service_accessibility
from dhakagraph.config import EXPANDED_DHAKA_STUDY
from dhakagraph.urban import (
    classify_urban_functions,
    land_use_group,
    make_analysis_grid,
    service_group,
)


def test_analysis_grid_is_stable_and_contains_requested_anchors() -> None:
    grid = make_analysis_grid(EXPANDED_DHAKA_STUDY, cell_size_m=750)

    assert len(grid) > 500
    assert grid["cell_id"].is_unique
    assert grid.crs.to_epsg() == 32646
    union = grid.geometry.union_all()
    anchors = gpd.GeoSeries(
        [
            Point(longitude, latitude)
            for _, longitude, latitude in EXPANDED_DHAKA_STUDY.anchors_lon_lat
        ],
        crs="EPSG:4326",
    ).to_crs(grid.crs)
    assert all(union.covers(anchor) for anchor in anchors)


def test_category_reducers_create_interpretable_groups() -> None:
    assert land_use_group("residential") == "residential"
    assert land_use_group("university") == "institutional"
    assert land_use_group("playground") == "green_recreation"
    assert service_group("general_hospital") == "healthcare"
    assert service_group("shopping_mall") == "market"
    assert service_group("software_development") is None


def test_transparent_cluster_baseline_is_reproducible() -> None:
    values = np.linspace(0, 1, 60)
    cells = gpd.GeoDataFrame(
        {
            "building_footprint_share": values,
            "poi_density_km2": values * 100,
            "road_density_km_km2": values[::-1] * 20,
            "distance_healthcare_m": values[::-1] * 2_000,
        },
        geometry=[Point(index, 0) for index in range(60)],
        crs="EPSG:32646",
    )
    first = cells.copy()
    second = cells.copy()

    first_summary = classify_urban_functions(first, cluster_count=3, random_seed=42)
    second_summary = classify_urban_functions(second, cluster_count=3, random_seed=42)

    assert first["cluster_id"].tolist() == second["cluster_id"].tolist()
    assert first["urban_class"].notna().all()
    assert first_summary["cluster_count"] == 3
    assert first_summary == second_summary


def test_network_service_accessibility_uses_road_distance() -> None:
    nodes = gpd.GeoDataFrame(
        {"node_id": ["0", "1", "2"]},
        geometry=[Point(0, 0), Point(100, 0), Point(200, 0)],
        crs="EPSG:32646",
    )
    edges = gpd.GeoDataFrame(
        {
            "from_node_id": ["0", "1"],
            "to_node_id": ["1", "2"],
            "length": [100.0, 100.0],
        },
        geometry=[LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)])],
        crs="EPSG:32646",
    )
    categories = ["hospital", "school", "market", "park", "bus_station"]
    places = gpd.GeoDataFrame(
        {"categories": [f'{{"primary":"{category}"}}' for category in categories]},
        geometry=[Point(0, 0)] * len(categories),
        crs="EPSG:32646",
    )
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["near", "far"],
            "urban_class": ["test", "test"],
            "building_density_km2": [100.0, 200.0],
            "building_footprint_share": [0.1, 0.2],
            "landuse_residential_share": [0.1, 0.2],
        },
        geometry=[box(-10, -10, 10, 10), box(190, -10, 210, 10)],
        crs="EPSG:32646",
    )

    result, ranking, summary = build_service_accessibility(
        cells,
        places,
        nodes,
        edges,
    )

    assert result.loc[result["cell_id"] == "near", "walk_minutes_healthcare"].iloc[0] == 0
    assert result.loc[result["cell_id"] == "far", "walk_minutes_healthcare"].iloc[0] == 2.5
    assert result["walk_healthcare_10min_count"].tolist() == [1, 1]
    assert len(ranking) == 2
    assert summary["facility_counts"]["healthcare"] == 1
