"""Graph-based flood cascade simulation and network vulnerability modeling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
import geopandas as gpd
import networkx as nx
import numpy as np
from shapely.geometry import Point

from dhakagraph.config import EXPANDED_DHAKA_STUDY, StudyArea
from dhakagraph.overture import METRIC_CRS, load_or_download_overture, process_overture_roads


def project_root() -> Path:
    """Return repository root path."""
    return Path(__file__).resolve().parents[2]


def estimate_node_elevations(
    road_nodes: gpd.GeoDataFrame,
    water_gdf: gpd.GeoDataFrame,
) -> np.ndarray:
    """Estimate spatial ground elevation (meters) based on proximity to Dhaka water bodies."""
    metric_nodes = road_nodes.to_crs(METRIC_CRS)
    if water_gdf.empty:
        # Fallback gradient if water layer empty: low in south/west, higher in north
        y_min, y_max = metric_nodes.geometry.y.min(), metric_nodes.geometry.y.max()
        norm_y = (metric_nodes.geometry.y - y_min) / max(y_max - y_min, 1.0)
        return 2.0 + 5.0 * norm_y.to_numpy()

    metric_water = water_gdf.to_crs(METRIC_CRS)
    # Calculate distance of each road node to closest water body
    water_union = metric_water.union_all()
    distances = metric_nodes.geometry.distance(water_union).to_numpy()

    # Elevation model: low near water, rising log-scale on higher ground.
    elevations = 1.2 + 1.8 * np.log1p(distances / 100.0)
    return np.clip(elevations, 1.0, 10.0)


def build_flood_model(
    area: StudyArea = EXPANDED_DHAKA_STUDY,
    water_levels_m: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0),
) -> dict[str, Any]:
    """Simulate network disruption under multi-stage flood inundation scenarios."""
    root = project_root()
    raw_dir = root / "data" / "raw"
    layers, _ = load_or_download_overture(area, raw_dir, types=("segment", "connector", "water"))

    processed_roads, road_nodes, road_edges = process_overture_roads(layers)
    water_gdf = layers.get("water", gpd.GeoDataFrame())

    nodes_proj = road_nodes.to_crs(METRIC_CRS).copy()
    if "node_id" not in nodes_proj:
        nodes_proj["node_id"] = nodes_proj.index.astype(str)
    nodes_proj["elevation_m"] = estimate_node_elevations(road_nodes, water_gdf)
    elev_lookup = dict(
        zip(
            nodes_proj["node_id"].astype(str),
            nodes_proj["elevation_m"],
            strict=True,
        )
    )

    # Build base NetworkX graph
    base_graph = nx.Graph()
    for row in nodes_proj.itertuples():
        base_graph.add_node(
            str(row.node_id),
            x=row.geometry.x,
            y=row.geometry.y,
            elevation=row.elevation_m,
        )

    edges_proj = road_edges.to_crs(METRIC_CRS).reset_index()
    for row in edges_proj.itertuples():
        u = str(row.from_node_id)
        v = str(row.to_node_id)
        if u not in base_graph or v not in base_graph or u == v:
            continue
        length = float(getattr(row, "length", row.geometry.length))
        min_elev = min(elev_lookup.get(u, 5.0), elev_lookup.get(v, 5.0))
        base_graph.add_edge(u, v, length=length, min_elevation=min_elev, geometry=row.geometry)

    # Baseline anchor connectivity (Airport, Uttara, Mirpur, Gulshan, Sayedabad)
    anchors = area.anchors_lon_lat
    anchor_nodes: dict[str, str] = {}
    for name, lon, lat in anchors:
        pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(METRIC_CRS).iloc[0]
        closest = min(
            base_graph.nodes(data=True),
            key=lambda n: ((n[1]["x"] - pt.x) ** 2 + (n[1]["y"] - pt.y) ** 2),
        )[0]
        anchor_nodes[name] = closest

    scenario_results = []
    vulnerable_edges_counts: dict[tuple[str, str], int] = {}

    for wl in water_levels_m:
        # An edge is inundated if its minimum elevation is <= water level
        surviving_edges = [
            (u, v, data)
            for u, v, data in base_graph.edges(data=True)
            if data["min_elevation"] > wl
        ]
        sub_graph = nx.Graph()
        sub_graph.add_nodes_from(base_graph.nodes(data=True))
        sub_graph.add_edges_from(surviving_edges)

        components = list(nx.connected_components(sub_graph))
        largest_comp_size = max(len(c) for c in components) if components else 0

        # Anchor pair reachability
        reachable_anchors = 0
        total_anchor_pairs = 0
        anchor_names = list(anchor_nodes.keys())
        for i in range(len(anchor_names)):
            for j in range(i + 1, len(anchor_names)):
                total_anchor_pairs += 1
                u_anc = anchor_nodes[anchor_names[i]]
                v_anc = anchor_nodes[anchor_names[j]]
                if nx.has_path(sub_graph, u_anc, v_anc):
                    reachable_anchors += 1

        inundated_edge_count = base_graph.number_of_edges() - sub_graph.number_of_edges()

        # Track inundated edges for vulnerability ranking
        for u, v, data in base_graph.edges(data=True):
            if data["min_elevation"] <= wl:
                pair = tuple(sorted([u, v]))
                vulnerable_edges_counts[pair] = vulnerable_edges_counts.get(pair, 0) + 1

        scenario_results.append(
            {
                "water_level_m": wl,
                "surviving_edges": sub_graph.number_of_edges(),
                "inundated_edges": inundated_edge_count,
                "inundated_edge_percent": round(
                    100.0 * inundated_edge_count / max(base_graph.number_of_edges(), 1),
                    2,
                ),
                "connected_components": len(components),
                "largest_component_nodes": largest_comp_size,
                "largest_component_share": round(
                    largest_comp_size / max(base_graph.number_of_nodes(), 1),
                    4,
                ),
                "connected_anchor_pairs": f"{reachable_anchors}/{total_anchor_pairs}",
            }
        )

    # Vulnerability ranking of edges
    ranked_vulnerable_edges = []
    for (u, v), freq in sorted(
        vulnerable_edges_counts.items(), key=lambda x: x[1], reverse=True
    )[:50]:
        data = base_graph[u][v]
        ranked_vulnerable_edges.append(
            {
                "node_from": u,
                "node_to": v,
                "min_elevation_m": round(data["min_elevation"], 2),
                "length_m": round(data["length"], 1),
                "inundation_frequency": freq,
            }
        )

    return {
        "base_nodes": base_graph.number_of_nodes(),
        "base_edges": base_graph.number_of_edges(),
        "base_graph_components": nx.number_connected_components(base_graph),
        "scenarios": scenario_results,
        "vulnerable_edges": ranked_vulnerable_edges,
        "base_graph": base_graph,
        "nodes_gdf": road_nodes,
        "edges_gdf": road_edges,
    }


def export_flood_outputs(
    flood_model: dict[str, Any],
    area: StudyArea,
    output_html: Path,
    output_summary_json: Path,
) -> None:
    """Generate interactive Folium flood scenario map and summary JSON."""
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_summary_json.parent.mkdir(parents=True, exist_ok=True)

    base_graph = flood_model["base_graph"]

    summary = {
        "study_area": area.name,
        "base_nodes": flood_model["base_nodes"],
        "base_edges": flood_model["base_edges"],
        "base_graph_components": flood_model.get("base_graph_components"),
        "scenarios": flood_model["scenarios"],
        "vulnerable_edges_top50": flood_model["vulnerable_edges"],
        "elevation_model": "Distance-to-water proxy, clipped to 1-10 m",
        "interpretation": (
            "Modeled network disruption scenarios for sensitivity analysis; "
            "not observed flood depths or an official hazard forecast."
        ),
        "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
    }
    output_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    m = folium.Map(
        location=[area.center_lat, area.center_lon],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    # Color scale for water levels
    colors = {0.5: "#FCD34D", 1.0: "#F59E0B", 1.5: "#EF4444", 2.0: "#B91C1C", 3.0: "#7F1D1D"}

    for wl in (0.5, 1.0, 1.5, 2.0, 3.0):
        fg = folium.FeatureGroup(name=f"Inundated Roads @ {wl}m Flood Level", show=(wl == 1.5))
        for _u, _v, data in base_graph.edges(data=True):
            if data["min_elevation"] <= wl:
                geom = data.get("geometry")
                if geom is not None and not geom.is_empty:
                    # Convert to WGS84 coords
                    g_wgs = gpd.GeoSeries([geom], crs=METRIC_CRS).to_crs("EPSG:4326").iloc[0]
                    coords = [(pt[1], pt[0]) for pt in g_wgs.coords]
                    folium.PolyLine(
                        coords,
                        color=colors.get(wl, "#EF4444"),
                        weight=3,
                        opacity=0.8,
                        popup=f"Min Elev: {data['min_elevation']:.2f}m (Inundated @ {wl}m)",
                    ).add_to(fg)
        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))
