"""Interactive map generation for DhakaGraph outputs."""

from pathlib import Path
from typing import Any

import folium
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox

from dhakagraph.config import StudyArea


def _centrality_color(relative_score: float) -> str:
    if relative_score >= 0.67:
        return "#b2182b"
    if relative_score >= 0.34:
        return "#ef8a62"
    return "#fddbc7"


def build_centrality_map(
    graph: nx.MultiDiGraph,
    ranked_nodes: list[dict[str, Any]],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Render the road network and its most central intersections to HTML."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    map_object = folium.Map(location=list(area.center), zoom_start=13, tiles=None)
    folium.TileLayer("CartoDB positron", name="Light basemap", control=True).add_to(map_object)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(map_object)

    edges = ox.convert.graph_to_gdfs(graph, nodes=False, edges=True)
    road_layer = folium.FeatureGroup(name="OSM drive network", show=True)
    folium.GeoJson(
        edges[["geometry"]].to_json(),
        style_function=lambda _feature: {
            "color": "#4d4d4d",
            "weight": 1.1,
            "opacity": 0.55,
        },
    ).add_to(road_layer)
    road_layer.add_to(map_object)

    centrality_layer = folium.FeatureGroup(name="Top structural intersections", show=True)
    max_score = max((record["betweenness"] for record in ranked_nodes), default=1.0) or 1.0
    for record in ranked_nodes:
        relative_score = record["betweenness"] / max_score
        tooltip = (
            f"Rank {record['rank']} | betweenness={record['betweenness']:.5f} "
            f"| degree={record['degree']} | {record['street_names'] or 'unnamed roads'}"
        )
        folium.CircleMarker(
            location=[record["latitude"], record["longitude"]],
            radius=4 + 7 * relative_score,
            color="#7f0000",
            weight=1,
            fill=True,
            fill_color=_centrality_color(relative_score),
            fill_opacity=0.9,
            tooltip=tooltip,
        ).add_to(centrality_layer)
    centrality_layer.add_to(map_object)

    title = (
        "<div style='position:fixed;top:10px;left:50px;z-index:9999;background:white;"
        "padding:8px 12px;border:1px solid #777;font:14px sans-serif'>"
        f"<b>DhakaGraph</b><br>{area.name}<br>"
        "Structural centrality—not live traffic"
        "</div>"
    )
    map_object.get_root().html.add_child(folium.Element(title))
    folium.LayerControl(collapsed=False).add_to(map_object)
    map_object.save(output_path)
    return output_path


def build_static_preview(
    graph: nx.MultiDiGraph,
    ranked_nodes: list[dict[str, Any]],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Create a compact PNG preview for quick visual quality assurance."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges = ox.convert.graph_to_gdfs(graph, nodes=False, edges=True).to_crs(epsg=32646)

    figure, axis = plt.subplots(figsize=(10, 10), dpi=160)
    edges.plot(ax=axis, color="#8c8c8c", linewidth=0.45, alpha=0.55)

    if ranked_nodes:
        points = ox.projection.project_gdf(
            ox.convert.graph_to_gdfs(graph, nodes=True, edges=False).loc[
                [int(record["node_id"]) for record in ranked_nodes]
            ],
            to_crs="EPSG:32646",
        )
        max_score = max(record["betweenness"] for record in ranked_nodes) or 1.0
        sizes = [25 + 180 * record["betweenness"] / max_score for record in ranked_nodes]
        points.plot(ax=axis, color="#b2182b", markersize=sizes, alpha=0.85, zorder=3)
        for record, point in zip(ranked_nodes[:10], points.geometry.iloc[:10], strict=True):
            axis.annotate(
                str(record["rank"]),
                (point.x, point.y),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
                color="#4d0000",
                zorder=4,
            )

    axis.set_title(f"DhakaGraph — {area.name}\nTop structural intersections", fontsize=13)
    axis.set_axis_off()
    figure.text(
        0.01,
        0.01,
        "© OpenStreetMap contributors, ODbL | Structural centrality, not live traffic",
        fontsize=7,
        color="#555555",
    )
    figure.tight_layout()
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)
    return output_path
