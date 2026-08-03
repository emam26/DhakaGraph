"""Static and interactive visualizations for the Dhaka Overture Maps audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from folium.plugins import FastMarkerCluster, Fullscreen
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import Point, box

from dhakagraph.config import StudyArea
from dhakagraph.overture import (
    METRIC_CRS,
    poi_group,
    poi_primary_category,
    poi_primary_name,
)

POI_COLORS = {
    "Healthcare": "#d73027",
    "Education": "#4575b4",
    "Food & drink": "#f46d43",
    "Retail & markets": "#984ea3",
    "Transport": "#1b9e77",
    "Civic & religious": "#8c6d31",
    "Recreation & culture": "#4daf4a",
    "Other": "#6b7280",
}

LAND_USE_COLORS = {
    "residential": "#e6cf72",
    "commercial": "#e78aa0",
    "industrial": "#9e5b8a",
    "education": "#6f9fc7",
    "institutional": "#6f9fc7",
    "recreation": "#66a96f",
    "park": "#66a96f",
    "forest": "#3e8b57",
    "transportation": "#a9adb2",
    "agriculture": "#86c6d8",
}


def building_density_grid(
    buildings: gpd.GeoDataFrame,
    *,
    cell_size_m: int = 750,
) -> gpd.GeoDataFrame:
    """Aggregate building footprints to occupied square cells for a compact web layer."""
    if buildings.empty:
        return gpd.GeoDataFrame(
            {"building_count": [], "footprint_m2": []},
            geometry=[],
            crs=METRIC_CRS,
        )
    metric = buildings.to_crs(METRIC_CRS)
    centers = metric.geometry.centroid
    minx, miny, _, _ = metric.total_bounds
    x_index = np.floor((centers.x - minx) / cell_size_m).astype(int)
    y_index = np.floor((centers.y - miny) / cell_size_m).astype(int)
    frame = gpd.GeoDataFrame(
        {
            "x_index": x_index,
            "y_index": y_index,
            "footprint_m2": metric.geometry.area,
        },
        geometry=metric.geometry,
        crs=metric.crs,
    )
    grouped = frame.groupby(["x_index", "y_index"]).agg(
        building_count=("geometry", "size"),
        footprint_m2=("footprint_m2", "sum"),
    )
    records = []
    for (x_cell, y_cell), row in grouped.iterrows():
        x0 = minx + x_cell * cell_size_m
        y0 = miny + y_cell * cell_size_m
        records.append(
            {
                "building_count": int(row["building_count"]),
                "footprint_m2": round(float(row["footprint_m2"]), 1),
                "geometry": box(x0, y0, x0 + cell_size_m, y0 + cell_size_m),
            }
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=METRIC_CRS)


def _anchor_frame(area: StudyArea) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"label": [anchor[0] for anchor in area.anchors_lon_lat]},
        geometry=[Point(anchor[1], anchor[2]) for anchor in area.anchors_lon_lat],
        crs="EPSG:4326",
    )


def _land_use_color(value: Any) -> str:
    normalized = str(value or "").lower()
    for keyword, color in LAND_USE_COLORS.items():
        if keyword in normalized:
            return color
    return "#c7c7c7"


def build_overture_preview(
    layers: dict[str, gpd.GeoDataFrame],
    processed_roads: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Render the tutorial-style Overture layers and processed road topology."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metric = {name: gdf.to_crs(METRIC_CRS) for name, gdf in layers.items()}
    buildings = metric["building"]
    segments = metric["segment"]
    roads = segments.loc[segments.get("subtype", "") == "road"]
    places = metric["place"].copy()
    land_use = metric["land_use"].copy()
    water = metric["water"]
    anchors = _anchor_frame(area).to_crs(METRIC_CRS)

    if "categories" in places:
        places["poi_group"] = places["categories"].map(poi_primary_category).map(poi_group)
    else:
        places["poi_group"] = "Other"

    figure, axes = plt.subplots(2, 2, figsize=(17, 17), dpi=150)
    for axis in axes.flat:
        axis.set_facecolor("#f7f7f5")
        axis.set_axis_off()

    buildings.plot(ax=axes[0, 0], facecolor="#d9d2c3", edgecolor="none", alpha=0.75)
    if not water.empty:
        water.plot(ax=axes[0, 0], facecolor="#9ecae1", edgecolor="none", alpha=0.85)
    roads.plot(ax=axes[0, 0], color="#176d73", linewidth=0.28, alpha=0.82)
    axes[0, 0].set_title("Buildings, roads and water", fontsize=15, fontweight="bold")

    for group, color in POI_COLORS.items():
        subset = places.loc[places["poi_group"] == group]
        if not subset.empty:
            subset.plot(ax=axes[0, 1], color=color, markersize=2.2, alpha=0.7)
    roads.plot(ax=axes[0, 1], color="#b5b5b5", linewidth=0.18, alpha=0.32)
    axes[0, 1].set_title("Overture places by broad function", fontsize=15, fontweight="bold")
    axes[0, 1].legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor=color, label=group)
            for group, color in POI_COLORS.items()
        ],
        loc="lower left",
        fontsize=8,
        frameon=False,
    )

    if not land_use.empty and "class" in land_use:
        land_use["map_color"] = land_use["class"].map(_land_use_color)
        land_use.plot(ax=axes[1, 0], color=land_use["map_color"], edgecolor="white", linewidth=0.15)
    roads.plot(ax=axes[1, 0], color="#666666", linewidth=0.16, alpha=0.4)
    axes[1, 0].set_title("Mapped land use", fontsize=15, fontweight="bold")
    axes[1, 0].legend(
        handles=[
            Patch(facecolor=color, label=label.title())
            for label, color in LAND_USE_COLORS.items()
        ],
        loc="lower left",
        fontsize=7,
        frameon=False,
        ncol=2,
    )

    processed_roads.plot(ax=axes[1, 1], color="#355f72", linewidth=0.35, alpha=0.65)
    if not road_nodes.empty:
        road_nodes.plot(ax=axes[1, 1], color="#e76f51", markersize=0.8, alpha=0.7)
    axes[1, 1].set_title("Connector-split, graph-ready roads", fontsize=15, fontweight="bold")

    for axis in axes.flat:
        anchors.plot(
            ax=axis,
            color="#112f4a",
            marker="*",
            edgecolor="white",
            linewidth=0.4,
            markersize=95,
            zorder=8,
        )

    figure.suptitle(
        "DhakaGraph — Overture Maps urban layers",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.01,
        0.008,
        "© OpenStreetMap contributors, Overture Maps Foundation | "
        "Mapped coverage, not observed activity",
        fontsize=8,
        color="#555555",
    )
    figure.tight_layout(rect=(0, 0.02, 1, 0.98))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path


def _normalize_html(path: Path) -> None:
    rendered = path.read_text(encoding="utf-8")
    normalized = "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def build_overture_explorer(
    layers: dict[str, gpd.GeoDataFrame],
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Build a compact layer-controlled explorer for Overture coverage in Dhaka."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    map_object = folium.Map(
        location=list(area.center),
        zoom_start=11,
        tiles=None,
        prefer_canvas=True,
        control_scale=True,
    )
    folium.TileLayer("CartoDB positron", name="Light basemap", control=True).add_to(map_object)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(map_object)

    density = building_density_grid(layers["building"]).to_crs("EPSG:4326")
    if not density.empty:
        maximum = max(int(density["building_count"].quantile(0.95)), 1)

        def density_style(feature):
            ratio = min(feature["properties"]["building_count"] / maximum, 1.0)
            color = "#54278f" if ratio >= 0.67 else "#756bb1" if ratio >= 0.34 else "#9e9ac8"
            return {
                "fillColor": color,
                "color": color,
                "weight": 0.4,
                "fillOpacity": 0.18 + 0.5 * ratio,
            }

        folium.GeoJson(
            density.to_json(),
            name="Building density (750 m cells)",
            style_function=density_style,
            tooltip=folium.GeoJsonTooltip(
                fields=["building_count", "footprint_m2"],
                aliases=["Mapped buildings", "Footprint area (m²)"],
                localize=True,
            ),
            show=True,
        ).add_to(map_object)

    roads = layers["segment"]
    roads = roads.loc[roads.get("subtype", "") == "road"].to_crs(METRIC_CRS)
    roads = roads.set_geometry(roads.geometry.simplify(1.5)).to_crs("EPSG:4326")
    folium.GeoJson(
        roads[["geometry"]].to_json(),
        name="Overture road segments",
        style_function=lambda _feature: {"color": "#244e62", "weight": 0.75, "opacity": 0.58},
        smooth_factor=1.2,
        show=True,
    ).add_to(map_object)

    land_use = layers["land_use"].to_crs("EPSG:4326")
    if not land_use.empty:
        fields = [field for field in ("class", "subtype") if field in land_use]
        folium.GeoJson(
            land_use.to_json(),
            name="Overture land use",
            style_function=lambda feature: {
                "fillColor": _land_use_color(feature["properties"].get("class")),
                "color": "#777777",
                "weight": 0.35,
                "fillOpacity": 0.48,
            },
            tooltip=folium.GeoJsonTooltip(fields=fields) if fields else None,
            show=False,
        ).add_to(map_object)

    water = layers["water"].to_crs("EPSG:4326")
    if not water.empty:
        folium.GeoJson(
            water[["geometry"]].to_json(),
            name="Overture water",
            style_function=lambda _feature: {
                "fillColor": "#6baed6",
                "color": "#3182bd",
                "weight": 0.5,
                "fillOpacity": 0.55,
            },
            show=False,
        ).add_to(map_object)

    places = layers["place"].to_crs("EPSG:4326")
    if not places.empty:
        category_values = (
            places["categories"].map(poi_primary_category)
            if "categories" in places
            else ["uncategorized"] * len(places)
        )
        name_values = (
            places["names"].map(poi_primary_name)
            if "names" in places
            else ["Unnamed place"] * len(places)
        )
        place_records: dict[str, list[list[Any]]] = {group: [] for group in POI_COLORS}
        for geometry, name, category in zip(
            places.geometry,
            name_values,
            category_values,
            strict=True,
        ):
            if geometry is None or geometry.is_empty:
                continue
            point = geometry if geometry.geom_type == "Point" else geometry.representative_point()
            group = poi_group(category)
            place_records[group].append(
                [round(point.y, 6), round(point.x, 6), name, category]
            )

        for group, records in place_records.items():
            if not records:
                continue
            color = POI_COLORS[group]
            callback = f"""
                function (row) {{
                    var marker = L.circleMarker([row[0], row[1]], {{
                        radius: 4, color: '{color}', fillColor: '{color}',
                        fillOpacity: 0.76, weight: 0.7
                    }});
                    marker.bindTooltip('<b>' + row[2] + '</b><br>' + row[3]);
                    return marker;
                }}
            """
            FastMarkerCluster(
                data=records,
                callback=callback,
                name=f"Places — {group}",
                show=group in {"Healthcare", "Education", "Transport"},
            ).add_to(map_object)

    anchors = folium.FeatureGroup(name="Requested place anchors", show=True)
    for label, longitude, latitude in area.anchors_lon_lat:
        folium.CircleMarker(
            [latitude, longitude],
            radius=7,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color="#123b57",
            fill_opacity=1,
            tooltip=label,
        ).add_to(anchors)
    anchors.add_to(map_object)

    geometry = layers["segment"].to_crs("EPSG:4326")
    if area.geometry is not None:
        west, south, east, north = area.geometry.bounds
    else:
        west, south, east, north = geometry.total_bounds
    map_object.fit_bounds([[south, west], [north, east]])
    Fullscreen(position="topright").add_to(map_object)
    folium.LayerControl(position="topright", collapsed=True).add_to(map_object)

    map_object.get_root().header.add_child(
        folium.Element("<title>DhakaGraph — Overture Explorer</title>")
    )

    counts = summary["feature_counts"]
    panel = f"""
    <section style="position:fixed;left:18px;top:18px;z-index:9999;
      background:rgba(255,255,255,.94);border:1px solid #bbb;border-radius:8px;
      padding:10px 12px;font:13px/1.35 sans-serif;max-width:280px">
      <strong>DhakaGraph — Overture Explorer</strong><br>
      Release {summary['overture_release']}<br>
      {counts.get('building', 0):,} buildings · {counts.get('place', 0):,} places<br>
      {counts.get('segment', 0):,} transport segments ·
      {counts.get('land_use', 0):,} land-use features<br>
      <small>Mapped coverage, not observed visits or traffic.</small>
    </section>
    """
    map_object.get_root().html.add_child(folium.Element(panel))
    map_object.get_root().html.add_child(
        folium.Element(
            "<div style='position:fixed;right:8px;bottom:4px;z-index:9999;"
            "background:rgba(255,255,255,.8);padding:2px 5px;font:10px sans-serif'>"
            "© OpenStreetMap contributors, Overture Maps Foundation</div>"
        )
    )
    map_object.save(output_path)
    _normalize_html(output_path)
    return output_path
