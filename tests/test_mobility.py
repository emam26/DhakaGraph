"""Tests for modeled mobility pressure."""

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from dhakagraph.config import StudyArea
from dhakagraph.mobility import build_mobility_pressure


def test_mobility_pressure_routes_between_proxy_cells(tmp_path) -> None:
    nodes = gpd.GeoDataFrame(
        {"node_id": ["0", "1", "2"]},
        geometry=[Point(90, 23), Point(90.01, 23), Point(90.02, 23)],
        crs="EPSG:4326",
    )
    edges = gpd.GeoDataFrame(
        {"from_node_id": ["0", "1"], "to_node_id": ["1", "2"], "length": [1.0, 1.0]},
        geometry=[LineString([(90, 23), (90.01, 23)]), LineString([(90.01, 23), (90.02, 23)])],
        crs="EPSG:4326",
    )
    nodes_path, edges_path = tmp_path / "nodes.geojson", tmp_path / "edges.geojson"
    nodes.to_file(nodes_path, driver="GeoJSON")
    edges.to_file(edges_path, driver="GeoJSON")
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["a", "b", "c"],
            "building_density_km2": [10, 8, 1],
            "landuse_residential_share": [0.8, 0.7, 0.1],
            "building_footprint_share": [0.4, 0.3, 0.1],
            "poi_density_km2": [1, 5, 2],
            "poi_retail_markets_density_km2": [0, 4, 0],
            "poi_transport_density_km2": [0, 1, 0],
            "poi_healthcare_density_km2": [0, 0, 1],
            "poi_education_density_km2": [0, 0, 1],
        },
        geometry=[
            box(89.999, 22.999, 90.001, 23.001),
            box(90.009, 22.999, 90.011, 23.001),
            box(90.019, 22.999, 90.021, 23.001),
        ],
        crs="EPSG:4326",
    )
    area = StudyArea(slug="test", name="Test", center_lat=23, center_lon=90, radius_m=100)
    pressure_edges, pressure_nodes, rankings, summary = build_mobility_pressure(
        cells, nodes_path, edges_path, area, 2, 2
    )
    assert summary["routed_pairs"] > 0
    assert len(pressure_edges) > 0
    assert len(pressure_nodes) > 0
    assert rankings
