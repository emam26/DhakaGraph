"""OpenStreetMap acquisition and City2Graph conversion."""

from pathlib import Path

import city2graph as c2g
import geopandas as gpd
import networkx as nx
import osmnx as ox

from dhakagraph.config import StudyArea


def configure_osmnx(cache_dir: Path) -> None:
    """Configure deterministic local caching and concise console logging."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = True


def load_or_download_graph(
    area: StudyArea,
    raw_dir: Path,
    *,
    refresh: bool = False,
) -> tuple[nx.MultiDiGraph, Path]:
    """Load a cached graph or download a fresh point-centered OSM network."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    graph_path = raw_dir / f"{area.slug}_{area.network_type}.graphml"
    configure_osmnx(raw_dir / "osmnx_cache")

    if graph_path.exists() and not refresh:
        graph = ox.io.load_graphml(graph_path)
        return graph, graph_path

    graph = ox.graph.graph_from_point(
        area.center,
        dist=area.radius_m,
        network_type=area.network_type,
        simplify=True,
        retain_all=False,
    )
    graph.graph["dhakagraph_study_area"] = area.name
    graph.graph["dhakagraph_center"] = area.center
    graph.graph["dhakagraph_radius_m"] = area.radius_m
    ox.io.save_graphml(graph, graph_path)
    return graph, graph_path


def city2graph_frames(
    graph: nx.MultiDiGraph,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Convert an OSMnx graph into City2Graph's GeoDataFrame representation."""
    nodes, edges = c2g.nx_to_gdf(graph)
    if not isinstance(nodes, gpd.GeoDataFrame) or not isinstance(edges, gpd.GeoDataFrame):
        raise TypeError("Expected homogeneous node and edge GeoDataFrames")
    return nodes, edges


def export_spatial_layers(
    nodes: gpd.GeoDataFrame,
    edges: gpd.GeoDataFrame,
    processed_dir: Path,
    slug: str,
) -> tuple[Path, Path]:
    """Write compact, interoperable GeoJSON layers for manual GIS inspection."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = processed_dir / f"{slug}_nodes.geojson"
    edges_path = processed_dir / f"{slug}_edges.geojson"

    node_columns = [column for column in ("street_count", "geometry") if column in nodes]
    edge_columns = [column for column in ("length", "oneway", "geometry") if column in edges]

    node_export = nodes[node_columns].copy().reset_index()
    edge_export = edges[edge_columns].copy().reset_index()

    node_export.to_file(nodes_path, driver="GeoJSON")
    edge_export.to_file(edges_path, driver="GeoJSON")
    return nodes_path, edges_path
