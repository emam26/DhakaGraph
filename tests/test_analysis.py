import networkx as nx

from dhakagraph.analysis import (
    approximate_betweenness,
    graph_summary,
    rank_intersections,
    to_simple_undirected,
)


def _toy_multidigraph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node_id in range(4):
        graph.add_node(node_id, x=90.39 + node_id * 0.001, y=23.73)
    graph.add_edge(0, 1, length=100, name="Road A")
    graph.add_edge(1, 0, length=120)
    graph.add_edge(1, 2, length=100)
    graph.add_edge(2, 3, length=100)
    return graph


def test_multidigraph_collapses_to_shortest_undirected_edges() -> None:
    simple = to_simple_undirected(_toy_multidigraph())
    assert simple.number_of_edges() == 3
    assert simple[0][1]["length"] == 100


def test_path_middle_nodes_have_highest_betweenness() -> None:
    simple = to_simple_undirected(_toy_multidigraph())
    scores = approximate_betweenness(simple, samples=10, seed=42)
    assert scores[1] == scores[2]
    assert scores[1] > scores[0]


def test_summary_and_rankings_are_serializable_records() -> None:
    original = _toy_multidigraph()
    simple = to_simple_undirected(original)
    summary = graph_summary(original, simple)
    rankings = rank_intersections(
        simple,
        approximate_betweenness(simple, samples=10, seed=42),
        limit=2,
    )
    assert summary["connected_components"] == 1
    assert summary["structural_road_length_km"] == 0.3
    assert len(rankings) == 2
    assert isinstance(rankings[0]["node_id"], str)
    assert "street_names" in rankings[0]
