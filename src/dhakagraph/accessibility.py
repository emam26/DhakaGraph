"""Road-network service accessibility and service-desert analysis."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree

from dhakagraph.overture import METRIC_CRS, poi_primary_category
from dhakagraph.urban import service_group

SERVICE_GROUPS = ("healthcare", "education", "market", "park", "transport")
WALK_SPEED_M_PER_MIN = 80.0
WALK_THRESHOLDS_MIN = (10, 15, 30)


def _metric_points(gdf: gpd.GeoDataFrame, crs: str = METRIC_CRS) -> gpd.GeoDataFrame:
    frame = gdf.to_crs(crs).copy()
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]
    frame.geometry = frame.geometry.representative_point()
    return frame


def build_walk_graph(
    road_nodes: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
) -> tuple[nx.Graph, gpd.GeoDataFrame]:
    """Build a simple undirected length-weighted graph from Overture products."""
    nodes = road_nodes.to_crs(METRIC_CRS).copy()
    nodes["node_id"] = nodes["node_id"].astype(str)
    graph = nx.Graph()
    for row in nodes.itertuples():
        graph.add_node(str(row.node_id), x=float(row.geometry.x), y=float(row.geometry.y))

    edges = road_edges.to_crs(METRIC_CRS)
    for row in edges.itertuples():
        source = str(row.from_node_id)
        target = str(row.to_node_id)
        if source == target or source not in graph or target not in graph:
            continue
        raw_length = getattr(row, "length", None)
        try:
            length = float(raw_length)
        except (TypeError, ValueError):
            length = float(row.geometry.length)
        if not np.isfinite(length) or length <= 0:
            length = float(row.geometry.length)
        if graph.has_edge(source, target):
            if length < graph[source][target]["length"]:
                graph[source][target].update(length=length)
            continue
        graph.add_edge(source, target, length=length)
    components = list(nx.connected_components(graph))
    largest = max(components, key=len) if components else set()
    analysis_graph = graph.subgraph(largest).copy()
    analysis_graph.graph.update(
        {
            "source_components": len(components),
            "source_nodes": graph.number_of_nodes(),
            "excluded_small_component_nodes": graph.number_of_nodes()
            - analysis_graph.number_of_nodes(),
        }
    )
    nodes = nodes.loc[nodes["node_id"].isin(largest)].copy()
    return analysis_graph, nodes


def snap_points_to_nodes(
    points: gpd.GeoSeries,
    nodes: gpd.GeoDataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the nearest graph-node ID and snap distance for each point."""
    metric_points = gpd.GeoSeries(points, crs=points.crs).to_crs(nodes.crs)
    point_xy = np.column_stack((metric_points.x.to_numpy(), metric_points.y.to_numpy()))
    node_xy = np.column_stack((nodes.geometry.x.to_numpy(), nodes.geometry.y.to_numpy()))
    distances, indices = cKDTree(node_xy).query(point_xy, k=1)
    node_ids = nodes["node_id"].astype(str).to_numpy()
    return node_ids[np.asarray(indices)], np.asarray(distances)


def prepare_service_points(places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Extract the service categories used in the accessibility study."""
    points = _metric_points(places)
    points["primary_category"] = (
        points["categories"].map(poi_primary_category)
        if "categories" in points
        else "uncategorized"
    )
    points["service_group"] = points["primary_category"].map(service_group)
    return points.loc[points["service_group"].isin(SERVICE_GROUPS)].copy()


def _service_node_counts(
    services: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
) -> dict[str, CounterLike]:
    services = services.copy()
    services["walk_node"], services["walk_snap_distance_m"] = snap_points_to_nodes(
        services.geometry,
        nodes,
    )
    counts: dict[str, CounterLike] = {}
    for group in SERVICE_GROUPS:
        group_nodes = services.loc[services["service_group"] == group, "walk_node"]
        counts[group] = CounterLike(group_nodes.value_counts().to_dict())
    return counts


class CounterLike(dict[str, int]):
    """Typed dictionary for counts of services snapped to graph nodes."""

    def get_count(self, node_id: str) -> int:
        return int(self.get(node_id, 0))


def _network_walk_metrics(
    cells: gpd.GeoDataFrame,
    graph: nx.Graph,
    nodes: gpd.GeoDataFrame,
    service_counts: Mapping[str, CounterLike],
) -> None:
    cell_points = cells.geometry.representative_point()
    cells["walk_node"], cells["walk_snap_distance_m"] = snap_points_to_nodes(
        cell_points,
        nodes,
    )

    for group in SERVICE_GROUPS:
        sources = list(service_counts[group])
        distances = (
            nx.multi_source_dijkstra_path_length(graph, sources, weight="length")
            if sources
            else {}
        )
        cells[f"walk_distance_{group}_m"] = (
            cells["walk_node"].map(distances) + cells["walk_snap_distance_m"]
        )
        cells[f"walk_minutes_{group}"] = (
            cells[f"walk_distance_{group}_m"] / WALK_SPEED_M_PER_MIN
        )
        cells[f"walk_unreachable_{group}"] = cells[f"walk_minutes_{group}"].isna()

    maximum_distance = max(WALK_THRESHOLDS_MIN) * WALK_SPEED_M_PER_MIN
    unique_nodes = cells["walk_node"].unique()
    reachable: dict[str, dict[str, dict[int, int]]] = {
        node: {
            group: {threshold: 0 for threshold in WALK_THRESHOLDS_MIN}
            for group in SERVICE_GROUPS
        }
        for node in unique_nodes
    }
    for node in unique_nodes:
        lengths = nx.single_source_dijkstra_path_length(
            graph,
            node,
            cutoff=maximum_distance,
            weight="length",
        )
        snap_distance = float(
            cells.loc[cells["walk_node"] == node, "walk_snap_distance_m"].iloc[0]
        )
        for destination, distance in lengths.items():
            distance += snap_distance
            for group in SERVICE_GROUPS:
                count = service_counts[group].get_count(destination)
                if count == 0:
                    continue
                for threshold in WALK_THRESHOLDS_MIN:
                    if distance <= threshold * WALK_SPEED_M_PER_MIN:
                        reachable[node][group][threshold] += count

    for group in SERVICE_GROUPS:
        for threshold in WALK_THRESHOLDS_MIN:
            column = f"walk_{group}_{threshold}min_count"
            cells[column] = cells["walk_node"].map(
                {node: values[group][threshold] for node, values in reachable.items()}
            )


def _drive_metrics(
    cells: gpd.GeoDataFrame,
    services: gpd.GeoDataFrame,
    drive_graph: nx.MultiDiGraph,
) -> None:
    graph = drive_graph.copy()
    if not all("speed_kph" in data for _, _, data in graph.edges(data=True)):
        graph = ox.add_edge_speeds(graph)
    if not all("travel_time" in data for _, _, data in graph.edges(data=True)):
        graph = ox.add_edge_travel_times(graph)

    cell_wgs84 = cells.to_crs("EPSG:4326").geometry.representative_point()
    cells["drive_node"] = ox.distance.nearest_nodes(
        graph,
        X=cell_wgs84.x.to_numpy(),
        Y=cell_wgs84.y.to_numpy(),
    )
    service_wgs84 = services.to_crs("EPSG:4326")
    services = services.copy()
    services["drive_node"] = ox.distance.nearest_nodes(
        graph,
        X=service_wgs84.geometry.x.to_numpy(),
        Y=service_wgs84.geometry.y.to_numpy(),
    )
    reverse = graph.reverse(copy=False)
    for group in SERVICE_GROUPS:
        sources = (
            services.loc[services["service_group"] == group, "drive_node"].unique().tolist()
        )
        times = (
            nx.multi_source_dijkstra_path_length(reverse, sources, weight="travel_time")
            if sources
            else {}
        )
        cells[f"drive_minutes_{group}"] = cells["drive_node"].map(times) / 60.0
        cells[f"walk_drive_ratio_{group}"] = (
            cells[f"walk_minutes_{group}"] / cells[f"drive_minutes_{group}"].replace(0, np.nan)
        )


def _percentile(values: pd.Series, *, high_is_good: bool = True) -> pd.Series:
    ranked = values.rank(pct=True, method="average")
    return ranked if high_is_good else 1 - ranked


def add_service_desert_scores(cells: gpd.GeoDataFrame) -> None:
    """Attach transparent access-gap and built-demand proxy scores."""
    demand = pd.concat(
        [
            _percentile(cells["building_density_km2"]),
            _percentile(cells["building_footprint_share"]),
            _percentile(cells["landuse_residential_share"]),
        ],
        axis=1,
    ).mean(axis=1)
    gap_parts = []
    service_gap_columns: dict[str, pd.Series] = {}
    for group in ("healthcare", "education", "market", "park"):
        nearest = cells[f"walk_minutes_{group}"].fillna(cells[f"walk_minutes_{group}"].max())
        count = cells[f"walk_{group}_15min_count"].fillna(0)
        gap = pd.concat(
            [_percentile(nearest), _percentile(count, high_is_good=False)],
            axis=1,
        ).mean(axis=1)
        service_gap_columns[group] = gap
        gap_parts.append(gap)

    overall_gap = pd.concat(gap_parts, axis=1).mean(axis=1)
    cells["built_intensity_proxy"] = demand * 100
    cells["service_gap_score"] = overall_gap * 100
    cells["service_desert_score"] = overall_gap * (0.4 + 0.6 * demand) * 100
    gap_frame = pd.DataFrame(service_gap_columns)
    cells["largest_service_gap"] = gap_frame.idxmax(axis=1)
    unreachable_columns = [
        f"walk_unreachable_{group}" for group in ("healthcare", "education", "market", "park")
    ]
    cells["walk_unreachable_service_count"] = cells[unreachable_columns].sum(axis=1)
    cells.loc[cells["walk_unreachable_service_count"] >= 2, "largest_service_gap"] = (
        "multiple/unreachable"
    )


def rank_service_deserts(cells: gpd.GeoDataFrame, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return the highest demand-adjusted service-gap cells."""
    columns = [
        "cell_id",
        "urban_class",
        "service_desert_score",
        "service_gap_score",
        "built_intensity_proxy",
        "largest_service_gap",
        "walk_unreachable_service_count",
        *[f"walk_minutes_{group}" for group in ("healthcare", "education", "market", "park")],
        *[f"walk_{group}_15min_count" for group in ("healthcare", "education", "market", "park")],
    ]
    ranked = cells.nlargest(limit, "service_desert_score")[columns].copy()
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked.round(3).to_dict(orient="records")


def build_service_accessibility(
    cells: gpd.GeoDataFrame,
    places: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
    drive_graph: nx.MultiDiGraph | None = None,
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Calculate walking/driving access and demand-adjusted service gaps."""
    output = cells.to_crs(METRIC_CRS).copy()
    services = prepare_service_points(places)
    walk_graph, nodes = build_walk_graph(road_nodes, road_edges)
    service_counts = _service_node_counts(services, nodes)
    _network_walk_metrics(output, walk_graph, nodes, service_counts)
    if drive_graph is not None:
        _drive_metrics(output, services, drive_graph)
    add_service_desert_scores(output)
    ranking = rank_service_deserts(output)

    facility_counts = services["service_group"].value_counts()
    walk_statistics = {}
    for group in SERVICE_GROUPS:
        values = output[f"walk_minutes_{group}"].dropna()
        walk_statistics[group] = {
            "median_nearest_minutes": round(float(values.median()), 2),
            "p90_nearest_minutes": round(float(values.quantile(0.9)), 2),
            "median_reachable_15min": round(
                float(output[f"walk_{group}_15min_count"].median()),
                1,
            ),
        }
    summary = {
        "method": "Network shortest paths from 750 m cell representative points",
        "walk_speed_km_h": WALK_SPEED_M_PER_MIN * 60 / 1_000,
        "walk_thresholds_minutes": list(WALK_THRESHOLDS_MIN),
        "walk_network": "Undirected connector-split Overture road graph",
        "walk_graph_nodes": walk_graph.number_of_nodes(),
        "walk_graph_edges": walk_graph.number_of_edges(),
        "walk_graph_components": nx.number_connected_components(walk_graph),
        "walk_source_components": walk_graph.graph.get("source_components", 1),
        "walk_excluded_small_component_nodes": walk_graph.graph.get(
            "excluded_small_component_nodes",
            0,
        ),
        "median_cell_snap_distance_m": round(float(output["walk_snap_distance_m"].median()), 2),
        "p90_cell_snap_distance_m": round(
            float(output["walk_snap_distance_m"].quantile(0.9)),
            2,
        ),
        "drive_network": "Directed OSM drive graph with OSMnx-inferred speeds"
        if drive_graph is not None
        else "Not modeled",
        "transit_network": "Not modeled: no validated Dhaka GTFS feed is included",
        "facility_counts": {
            group: int(facility_counts.get(group, 0)) for group in SERVICE_GROUPS
        },
        "walk_statistics": walk_statistics,
        "unreachable_cell_counts": {
            group: int(output[f"walk_unreachable_{group}"].sum())
            for group in SERVICE_GROUPS
        },
        "service_desert_definition": (
            "Percentile-ranked nearest walking times and 15-minute facility counts, "
            "weighted by a mapped building/residential-intensity proxy."
        ),
        "interpretation": (
            "Modeled accessibility over mapped roads and facilities; not sidewalk quality, "
            "service capacity, population, congestion, or observed trips."
        ),
    }
    return output, ranking, summary
