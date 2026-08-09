"""Morphological dual graph construction and visualization matching city2graph specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import city2graph as c2g
import folium
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point

from dhakagraph.config import EXPANDED_DHAKA_STUDY, StudyArea
from dhakagraph.overture import METRIC_CRS, load_or_download_overture


def project_root() -> Path:
    """Return repository root path."""
    return Path(__file__).resolve().parents[2]


def build_morphological_graph(
    area: StudyArea = EXPANDED_DHAKA_STUDY,
    sample_radius_m: int = 1200,
) -> tuple[dict[str, gpd.GeoDataFrame], dict[tuple[str, str, str], gpd.GeoDataFrame]]:
    """Build a projected morphological graph over a representative central area of Dhaka."""
    root = project_root()
    raw_dir = root / "data" / "raw"
    layers, _ = load_or_download_overture(area, raw_dir, types=("building", "segment", "connector"))

    buildings = layers["building"].to_crs(METRIC_CRS)
    segments = layers["segment"].to_crs(METRIC_CRS)
    roads = segments.loc[segments.get("subtype", "") == "road"].copy()

    # Clip to sample radius around center for clean dual graph visualization
    center_pt = Point(area.center_lon, area.center_lat)
    center_series = gpd.GeoSeries([center_pt], crs="EPSG:4326").to_crs(METRIC_CRS)
    buffer_geom = center_series.buffer(sample_radius_m).iloc[0]

    sub_buildings = buildings.loc[buildings.geometry.intersects(buffer_geom)].copy()
    sub_roads = roads.loc[roads.geometry.intersects(buffer_geom)].copy()

    if len(sub_buildings) > 2500:
        sub_buildings = sub_buildings.sample(n=2500, random_state=42)

    nodes, edges = c2g.morphological_graph(
        buildings_gdf=sub_buildings,
        segments_gdf=sub_roads,
        center_point=center_series,
        distance=sample_radius_m,
    )
    return nodes, edges


def export_morphological_map(
    nodes: dict[str, gpd.GeoDataFrame],
    edges: dict[tuple[str, str, str], gpd.GeoDataFrame],
    area: StudyArea,
    output_html: Path,
    output_png: Path,
) -> dict[str, Any]:
    """Generate interactive Folium map and static matplotlib PNG preview."""
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    place_nodes = nodes["place"].to_crs("EPSG:4326")
    movement_nodes = nodes["movement"].to_crs("EPSG:4326")

    p2p_edges = edges.get(
        ("place", "touched_to", "place"), gpd.GeoDataFrame(geometry=[])
    ).to_crs("EPSG:4326")
    m2m_edges = edges.get(
        ("movement", "connected_to", "movement"), gpd.GeoDataFrame(geometry=[])
    ).to_crs("EPSG:4326")
    p2m_edges = edges.get(
        ("place", "faced_to", "movement"), gpd.GeoDataFrame(geometry=[])
    ).to_crs("EPSG:4326")

    m = folium.Map(
        location=[area.center_lat, area.center_lon],
        zoom_start=15,
        tiles="CartoDB positron",
    )

    # Center point star
    folium.Marker(
        [area.center_lat, area.center_lon],
        popup="Study Center Point (Shahbag/Dhaka)",
        icon=folium.Icon(color="black", icon="star"),
    ).add_to(m)

    # Layer Groups
    fg_m2m = folium.FeatureGroup(name="Public-to-Public (Street Connectors)", show=True)
    fg_p2p = folium.FeatureGroup(name="Private-to-Private (Building Adjacency)", show=True)
    fg_p2m = folium.FeatureGroup(name="Private-to-Public (Frontage Access)", show=True)
    fg_place = folium.FeatureGroup(name="Private Nodes (Place Parcels)", show=True)
    fg_move = folium.FeatureGroup(name="Public Nodes (Street Intersections)", show=True)

    # Draw edges
    for row in m2m_edges.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        coords = [(pt[1], pt[0]) for pt in row.geometry.coords]
        folium.PolyLine(coords, color="#2563EB", weight=2, opacity=0.8).add_to(fg_m2m)

    for row in p2p_edges.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        coords = [(pt[1], pt[0]) for pt in row.geometry.coords]
        folium.PolyLine(coords, color="#DC2626", weight=1.5, opacity=0.7).add_to(fg_p2p)

    for row in p2m_edges.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        coords = [(pt[1], pt[0]) for pt in row.geometry.coords]
        folium.PolyLine(
            coords, color="#7C3AED", weight=1.0, opacity=0.5, dash_array="4,4"
        ).add_to(fg_p2m)

    # Draw nodes
    for row in place_nodes.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        folium.CircleMarker(
            [row.geometry.y, row.geometry.x],
            radius=3,
            color="#DC2626",
            fill=True,
            fill_color="#DC2626",
            fill_opacity=0.9,
            popup="Private Building Parcel Node",
        ).add_to(fg_place)

    for row in movement_nodes.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        folium.CircleMarker(
            [row.geometry.y, row.geometry.x],
            radius=4,
            color="#2563EB",
            fill=True,
            fill_color="#2563EB",
            fill_opacity=0.9,
            popup="Public Street Connector Node",
        ).add_to(fg_move)

    fg_m2m.add_to(m)
    fg_p2p.add_to(m)
    fg_p2m.add_to(m)
    fg_place.add_to(m)
    fg_move.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))

    # Matplotlib static figure matching the reference image layout
    fig, ax = plt.subplots(figsize=(10, 10), dpi=300)
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#F3F4F6")

    # Plot edges
    if not m2m_edges.empty:
        m2m_edges.plot(
            ax=ax,
            color="#2563EB",
            linewidth=1.2,
            alpha=0.85,
            label="Public-to-Public (Street Links)",
        )
    if not p2p_edges.empty:
        p2p_edges.plot(
            ax=ax,
            color="#DC2626",
            linewidth=1.0,
            alpha=0.75,
            label="Private-to-Private (Adjacency)",
        )
    if not p2m_edges.empty:
        p2m_edges.plot(
            ax=ax,
            color="#7C3AED",
            linewidth=0.8,
            alpha=0.5,
            linestyle="--",
            label="Private-to-Public (Frontage)",
        )

    # Plot nodes
    if not place_nodes.empty:
        ax.scatter(
            place_nodes.geometry.x,
            place_nodes.geometry.y,
            c="#DC2626",
            s=12,
            zorder=5,
            label="Private Nodes (Buildings)",
        )
    if not movement_nodes.empty:
        ax.scatter(
            movement_nodes.geometry.x,
            movement_nodes.geometry.y,
            c="#2563EB",
            s=16,
            zorder=6,
            label="Public Nodes (Intersections)",
        )

    # Plot center point star
    ax.scatter(
        [area.center_lon],
        [area.center_lat],
        c="black",
        s=120,
        marker="*",
        zorder=10,
        label="Study Center Point",
    )

    ax.set_title(
        "Dhaka Heterogeneous Morphological Graph (City2Graph)",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Longitude (deg)", fontsize=10)
    ax.set_ylabel("Latitude (deg)", fontsize=10)
    ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="none", fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close(fig)

    return {
        "private_nodes": len(place_nodes),
        "public_nodes": len(movement_nodes),
        "public_to_public_edges": len(m2m_edges),
        "private_to_private_edges": len(p2p_edges),
        "private_to_public_edges": len(p2m_edges),
        "html_path": str(output_html),
        "png_path": str(output_png),
    }


def main() -> None:
    """Run morphological pipeline."""
    root = project_root()
    output_html = root / "outputs" / "maps" / "morphological_graph.html"
    output_png = root / "outputs" / "maps" / "morphological_preview.png"
    print("Building Dhaka Morphological Dual Graph...")
    nodes, edges = build_morphological_graph(EXPANDED_DHAKA_STUDY)
    summary = export_morphological_map(nodes, edges, EXPANDED_DHAKA_STUDY, output_html, output_png)
    print("Morphological Graph summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
