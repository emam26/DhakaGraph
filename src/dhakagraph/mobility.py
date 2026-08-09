"""Modeled movement pressure over the Dhaka road graph."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import Point

from dhakagraph.config import StudyArea
from dhakagraph.overture import METRIC_CRS


def _graph_from_files(nodes_path: Path, edges_path: Path) -> nx.Graph:
    nodes = gpd.read_file(nodes_path).to_crs(METRIC_CRS)
    edges = gpd.read_file(edges_path).to_crs(METRIC_CRS).rename(
        columns={"class": "road_class", "names": "road_names"}
    )
    graph = nx.Graph()
    for row in nodes.itertuples():
        node_id = str(row.node_id)
        graph.add_node(node_id, x=row.geometry.x, y=row.geometry.y)
    for row in edges.itertuples():
        u, v = str(row.from_node_id), str(row.to_node_id)
        if u == v or u not in graph or v not in graph:
            continue
        graph.add_edge(
            u,
            v,
            length=float(row.length),
            geometry=row.geometry,
            road_class=str(getattr(row, "road_class", "unknown")),
            names=str(getattr(row, "road_names", "")),
        )
    largest = max(nx.connected_components(graph), key=len)
    return graph.subgraph(largest).copy()


def _snap_cells(cells: gpd.GeoDataFrame, graph: nx.Graph) -> pd.Series:
    metric_cells = cells.to_crs(METRIC_CRS)
    points = metric_cells.geometry.representative_point()
    node_ids = list(graph.nodes)
    node_xy = np.array([(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in node_ids])
    point_xy = np.column_stack((points.x.to_numpy(), points.y.to_numpy()))
    _, indices = cKDTree(node_xy).query(point_xy, k=1)
    return pd.Series([node_ids[int(index)] for index in indices], index=cells.index)


def _minmax(values: pd.Series) -> pd.Series:
    values = values.astype(float).fillna(0)
    spread = values.max() - values.min()
    return (values - values.min()) / spread if spread > 0 else pd.Series(1.0, index=values.index)


def build_mobility_pressure(
    cells: gpd.GeoDataFrame,
    nodes_path: Path,
    edges_path: Path,
    area: StudyArea,
    origin_count: int = 80,
    destination_count: int = 80,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Route a deterministic origin-destination demand proxy through the largest graph component."""
    graph = _graph_from_files(nodes_path, edges_path)
    cells = cells.copy()
    cells["origin_demand_proxy"] = (
        np.log1p(cells.get("building_density_km2", 0).fillna(0))
        * (0.5 + cells.get("landuse_residential_share", 0).fillna(0))
        * (0.5 + cells.get("building_footprint_share", 0).fillna(0))
    )
    attraction = (
        cells.get("poi_density_km2", 0).fillna(0)
        + 4 * cells.get("poi_retail_markets_density_km2", 0).fillna(0)
        + 3 * cells.get("poi_transport_density_km2", 0).fillna(0)
        + 2 * cells.get("poi_healthcare_density_km2", 0).fillna(0)
        + 2 * cells.get("poi_education_density_km2", 0).fillna(0)
    )
    cells["destination_attraction_proxy"] = attraction
    cells["graph_node"] = _snap_cells(cells, graph)
    origins = cells.sort_values("origin_demand_proxy", ascending=False).head(origin_count)
    destinations = cells.sort_values(
        "destination_attraction_proxy", ascending=False
    ).head(destination_count)
    origin_weights = _minmax(origins["origin_demand_proxy"]) + 0.1
    destination_weights = _minmax(destinations["destination_attraction_proxy"]) + 0.1
    edge_pressure: defaultdict[tuple[str, str], float] = defaultdict(float)
    edge_routes: defaultdict[tuple[str, str], int] = defaultdict(int)
    node_pressure: defaultdict[str, float] = defaultdict(float)
    route_count = 0
    for origin_index, origin in origins.iterrows():
        source = origin["graph_node"]
        paths = nx.single_source_dijkstra_path(graph, source, weight="length")
        for destination_index, destination in destinations.iterrows():
            target = destination["graph_node"]
            path = paths.get(target)
            if not path or len(path) < 2 or origin_index == destination_index:
                continue
            demand = float(
                origin_weights.loc[origin_index] * destination_weights.loc[destination_index]
            )
            route_count += 1
            for u, v in zip(path[:-1], path[1:], strict=True):
                edge = tuple(sorted((str(u), str(v))))
                edge_pressure[edge] += demand
                edge_routes[edge] += 1
                node_pressure[str(u)] += demand
                node_pressure[str(v)] += demand

    edge_records: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        edge = tuple(sorted((str(u), str(v))))
        if edge not in edge_pressure:
            continue
        edge_records.append(
            {
                "node_from": str(u),
                "node_to": str(v),
                "pressure_score": round(edge_pressure[edge], 6),
                "route_count": edge_routes[edge],
                "road_class": data.get("road_class", "unknown"),
                "names": data.get("names", ""),
                "length_m": round(float(data.get("length", 0)), 2),
                "geometry": data["geometry"],
            }
        )
    pressure_edges = gpd.GeoDataFrame(edge_records, geometry="geometry", crs=METRIC_CRS)
    pressure_edges["pressure_percentile"] = (
        pressure_edges["pressure_score"].rank(pct=True).mul(100).round(3)
    )
    node_records = []
    for node, pressure in node_pressure.items():
        if node in graph.nodes:
            node_records.append(
                {
                    "node_id": node,
                    "pressure_score": round(pressure, 6),
                    "pressure_percentile": round(
                        float(pd.Series(node_pressure).rank(pct=True)[node] * 100), 3
                    ),
                    "geometry": Point(graph.nodes[node]["x"], graph.nodes[node]["y"]),
                }
            )
    pressure_nodes = gpd.GeoDataFrame(node_records, geometry="geometry", crs=METRIC_CRS)
    rankings = []
    for rank, (_, row) in enumerate(
        pressure_edges.nlargest(25, "pressure_score").iterrows(), start=1
    ):
        rankings.append(
            {
                "rank": rank,
                "node_from": row["node_from"],
                "node_to": row["node_to"],
                "pressure_score": row["pressure_score"],
                "route_count": int(row["route_count"]),
                "road_class": row["road_class"],
                "names": row["names"],
            }
        )
    summary = {
        "study_area": area.name,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "graph_components_used": 1,
        "origin_cells": len(origins),
        "destination_cells": len(destinations),
        "routed_pairs": route_count,
        "pressure_edges": len(pressure_edges),
        "method": (
            "Weighted origin-destination shortest paths over largest "
            "Overture graph component"
        ),
        "origin_proxy": "Mapped building density, footprint share, and residential land-use share",
        "destination_proxy": "Mapped POI, retail, transport, healthcare, and education density",
        "interpretation": (
            "Modeled potential movement pressure, not observed traffic volume "
            "or road usage."
        ),
    }
    return pressure_edges, pressure_nodes, rankings, summary
