"""Network-analysis helpers with no internet dependency."""

from collections.abc import Mapping
from typing import Any

import networkx as nx


def _length_m(attributes: Mapping[str, Any]) -> float:
    value = attributes.get("length", 1.0)
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return 1.0


def to_simple_undirected(graph: nx.Graph) -> nx.Graph:
    """Collapse a directed multigraph while retaining the shortest parallel edge."""
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes(data=True))

    for source, target, attributes in graph.edges(data=True):
        if source == target:
            continue
        length = _length_m(attributes)
        normalized_attributes = dict(attributes)
        normalized_attributes["length"] = length
        if simple.has_edge(source, target):
            if length < simple[source][target]["length"]:
                simple[source][target].update(normalized_attributes)
            continue
        simple.add_edge(source, target, **normalized_attributes)

    isolates = list(nx.isolates(simple))
    simple.remove_nodes_from(isolates)
    return simple


def largest_connected_component(graph: nx.Graph) -> nx.Graph:
    """Return a copied largest connected component."""
    if graph.number_of_nodes() == 0:
        return graph.copy()
    largest_nodes = max(nx.connected_components(graph), key=len)
    return graph.subgraph(largest_nodes).copy()


def graph_summary(original: nx.Graph, analysis_graph: nx.Graph) -> dict[str, Any]:
    """Return transparent structural statistics for the road network."""
    component_sizes = sorted(
        (len(component) for component in nx.connected_components(analysis_graph)),
        reverse=True,
    )
    total_length_m = sum(_length_m(data) for _, _, data in analysis_graph.edges(data=True))
    return {
        "original_graph_type": type(original).__name__,
        "original_nodes": original.number_of_nodes(),
        "original_directed_edges": original.number_of_edges(),
        "analysis_nodes": analysis_graph.number_of_nodes(),
        "analysis_undirected_edges": analysis_graph.number_of_edges(),
        "connected_components": len(component_sizes),
        "largest_component_nodes": component_sizes[0] if component_sizes else 0,
        "structural_road_length_km": round(total_length_m / 1_000, 3),
    }


def approximate_betweenness(
    graph: nx.Graph,
    *,
    samples: int,
    seed: int,
) -> dict[Any, float]:
    """Calculate exact or sampled length-weighted node betweenness centrality."""
    component = largest_connected_component(graph)
    node_count = component.number_of_nodes()
    if node_count == 0:
        return {}
    if node_count <= samples:
        return nx.betweenness_centrality(component, normalized=True, weight="length")
    return nx.betweenness_centrality(
        component,
        k=samples,
        normalized=True,
        weight="length",
        seed=seed,
    )


def _street_names(graph: nx.Graph, node_id: Any) -> str:
    """Collect readable OSM street names from edges incident on a node."""
    names: set[str] = set()
    for _, _, attributes in graph.edges(node_id, data=True):
        raw_name = attributes.get("name")
        if isinstance(raw_name, list):
            names.update(str(name) for name in raw_name if name)
        elif raw_name:
            names.add(str(raw_name))
    return " | ".join(sorted(names))


def rank_intersections(
    graph: nx.Graph,
    scores: Mapping[Any, float],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Create serializable records for the highest-betweenness intersections."""
    ranked: list[dict[str, Any]] = []
    for rank, (node_id, score) in enumerate(
        sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit],
        start=1,
    ):
        attributes = graph.nodes[node_id]
        ranked.append(
            {
                "rank": rank,
                "node_id": str(node_id),
                "betweenness": float(score),
                "degree": int(graph.degree(node_id)),
                "street_names": _street_names(graph, node_id),
                "latitude": float(attributes["y"]),
                "longitude": float(attributes["x"]),
            }
        )
    return ranked
