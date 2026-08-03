import networkx as nx

from dhakagraph.config import StudyArea
from dhakagraph.explorer import build_intersection_candidates, build_network_profile


def _sample_graph() -> tuple[nx.MultiDiGraph, nx.Graph]:
    original = nx.MultiDiGraph()
    simple = nx.Graph()
    for node_id, x, y in ((1, 90.0, 23.0), (2, 90.1, 23.0), (3, 90.2, 23.0)):
        original.add_node(node_id, x=x, y=y)
        simple.add_node(node_id, x=x, y=y)
    original.add_edge(1, 2, length=100, highway="primary", name="Alpha Road")
    original.add_edge(2, 3, length=200, highway="residential", name="Beta Road")
    simple.add_edge(1, 2, length=100, highway="primary", name="Alpha Road")
    simple.add_edge(2, 3, length=200, highway="residential", name="Beta Road")
    return original, simple


def test_candidates_union_centrality_and_degree_rankings() -> None:
    _, graph = _sample_graph()
    records = build_intersection_candidates(
        graph,
        {1: 0.9, 2: 0.1, 3: 0.0},
        centrality_limit=1,
        degree_limit=1,
    )
    assert {record["node_id"] for record in records} == {"1", "2"}
    assert next(record for record in records if record["node_id"] == "2")["degree"] == 2


def test_network_profile_summarizes_degrees_and_road_groups() -> None:
    original, graph = _sample_graph()
    area = StudyArea("sample", "Sample", 23.0, 90.1, radius_m=1_000)
    profile = build_network_profile(original, graph, {1: 0.0, 2: 0.4, 3: 0.0}, area)
    assert profile["degree_distribution"] == [
        {"degree": 1, "nodes": 2},
        {"degree": 2, "nodes": 1},
    ]
    assert profile["road_group_length_km"] == [
        {"group": "local", "length_km": 0.2},
        {"group": "arterial", "length_km": 0.1},
    ]
    assert profile["anchor_route"]["segments"] == []
