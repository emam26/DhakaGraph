"""Maps for the cell-based Dhaka urban-function atlas."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from dhakagraph.config import StudyArea

CLASS_COLORS = [
    "#2a9d8f",
    "#e76f51",
    "#457b9d",
    "#f4a261",
    "#8f5aa8",
    "#6a994e",
    "#bc6c25",
]

NUMERIC_METRICS = {
    "building_footprint_share": ("Building footprint", "%", 100.0, "#4a1486"),
    "building_density_km2": ("Buildings per km²", "", 1.0, "#7a0177"),
    "poi_density_km2": ("POIs per km²", "", 1.0, "#d95f0e"),
    "road_density_km_km2": ("Road density", " km/km²", 1.0, "#225ea8"),
    "intersection_density_km2": ("Intersections per km²", "", 1.0, "#006d2c"),
    "landuse_residential_share": ("Residential land use", "%", 100.0, "#d8b365"),
    "landuse_commercial_share": ("Commercial land use", "%", 100.0, "#d01c8b"),
    "landuse_industrial_share": ("Industrial land use", "%", 100.0, "#7b3294"),
    "landuse_green_share": ("Green/recreation land use", "%", 100.0, "#1b7837"),
    "distance_healthcare_m": ("Distance to healthcare", " m", 1.0, "#b2182b"),
    "distance_education_m": ("Distance to education", " m", 1.0, "#2166ac"),
    "distance_market_m": ("Distance to market", " m", 1.0, "#ef8a62"),
    "distance_transport_m": ("Distance to transport POI", " m", 1.0, "#018571"),
    "cell_betweenness_centrality": ("Cell betweenness", "", 1.0, "#542788"),
}


def _metric_configuration(cells: gpd.GeoDataFrame) -> dict[str, Any]:
    configuration: dict[str, Any] = {}
    sequential = ["#f7fbff", "#c6dbef", "#6baed6", "#3182bd", "#08519c", "#08306b"]
    for column, (label, unit, scale, accent) in NUMERIC_METRICS.items():
        if column not in cells:
            continue
        values = cells[column].replace([np.inf, -np.inf], np.nan).dropna() * scale
        if values.empty:
            breaks = [0.0] * 5
        else:
            breaks = [
                round(float(value), 4)
                for value in values.quantile([0.2, 0.4, 0.6, 0.8, 0.95]).to_list()
            ]
        colors = sequential[:-1] + [accent]
        configuration[column] = {
            "label": label,
            "unit": unit,
            "scale": scale,
            "breaks": breaks,
            "colors": colors,
        }
    return configuration


def build_urban_atlas_explorer(
    cells: gpd.GeoDataFrame,
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Write an interactive metric-switching Leaflet atlas."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    web_cells = cells.to_crs("EPSG:4326").copy()
    web_cells.geometry = web_cells.geometry.simplify(0.00001, preserve_topology=True)
    keep_columns = [
        "cell_id",
        "urban_class",
        "cluster_id",
        "area_km2",
        "building_count",
        "building_footprint_share",
        "building_density_km2",
        "poi_count",
        "poi_density_km2",
        "road_density_km_km2",
        "intersection_count",
        "intersection_density_km2",
        "landuse_residential_share",
        "landuse_commercial_share",
        "landuse_industrial_share",
        "landuse_institutional_share",
        "landuse_green_share",
        "distance_healthcare_m",
        "distance_education_m",
        "distance_market_m",
        "distance_park_m",
        "distance_transport_m",
        "cell_neighbor_count",
        "cell_betweenness_centrality",
        "geometry",
    ]
    keep_columns = [column for column in keep_columns if column in web_cells]
    geojson = json.loads(web_cells[keep_columns].to_json(drop_id=True))
    classes = sorted(cells["urban_class"].unique())
    class_colors = {
        label: CLASS_COLORS[index % len(CLASS_COLORS)] for index, label in enumerate(classes)
    }
    metrics = _metric_configuration(cells)
    anchors = [
        {"name": label, "longitude": longitude, "latitude": latitude}
        for label, longitude, latitude in area.anchors_lon_lat
    ]
    metric_options = "\n".join(
        ["<option value='urban_class'>Urban-function classes</option>"]
        + [
            f"<option value='{column}'>{config['label']}</option>"
            for column, config in metrics.items()
        ]
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dhaka Urban Function Atlas</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body, #map {{ height: 100%; margin: 0; font-family: Inter, system-ui, sans-serif; }}
    #map {{ background: #edf2f4; }}
    .panel {{ position: fixed; z-index: 1000; background: rgba(255,255,255,.96);
      border: 1px solid #c8d0d7; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,.12); }}
    #controls {{ left: 16px; top: 16px; width: min(330px, calc(100vw - 32px)); padding: 13px 14px; }}
    #details {{ left: 16px; bottom: 24px; width: min(330px, calc(100vw - 32px)); padding: 12px 14px; }}
    h1 {{ font-size: 17px; margin: 0 0 3px; }}
    .subtitle, .note {{ color: #4b5563; font-size: 12px; line-height: 1.35; }}
    label {{ display: block; font-size: 12px; font-weight: 650; margin: 10px 0 4px; }}
    select {{ width: 100%; border: 1px solid #aeb8c2; border-radius: 6px; padding: 7px; background: white; }}
    #legend {{ margin-top: 9px; display: grid; gap: 3px; font-size: 11px; }}
    .legend-row {{ display: flex; align-items: center; gap: 7px; }}
    .swatch {{ width: 15px; height: 11px; border: 1px solid rgba(0,0,0,.18); flex: 0 0 auto; }}
    .metric-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin-top: 8px; }}
    .metric-grid span {{ color: #64748b; font-size: 10px; display: block; }}
    .metric-grid strong {{ font-size: 13px; font-weight: 650; }}
    .leaflet-tooltip {{ font-size: 12px; }}
    @media (max-width: 600px) {{ #controls {{ max-height: 45vh; overflow-y: auto; }}
      #details {{ display: none; }} }}
  </style>
</head>
<body>
  <div id="map"></div>
  <section id="controls" class="panel">
    <h1>Dhaka Urban Function Atlas</h1>
    <div class="subtitle">{summary['cell_count']} analytical cells · {summary['cell_size_m']} m grid · Overture {summary.get('overture_release', '')}</div>
    <label for="metric">Map variable</label>
    <select id="metric">{metric_options}</select>
    <div id="legend"></div>
    <div class="note" style="margin-top:9px">Exploratory mapped structure—not administrative neighborhoods, population, activity or observed travel.</div>
  </section>
  <section id="details" class="panel">
    <strong id="cell-title">Select a cell</strong>
    <div id="cell-class" class="subtitle">Click a cell to inspect its urban profile.</div>
    <div id="cell-metrics" class="metric-grid"></div>
  </section>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const cells = {json.dumps(geojson, separators=(',', ':'))};
    const metrics = {json.dumps(metrics, separators=(',', ':'))};
    const classColors = {json.dumps(class_colors, separators=(',', ':'))};
    const anchors = {json.dumps(anchors, separators=(',', ':'))};
    const map = L.map('map', {{ preferCanvas: true, zoomControl: false }});
    L.control.zoom({{ position: 'topright' }}).addTo(map);
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }}).addTo(map);
    const anchorLayer = L.layerGroup().addTo(map);
    anchors.forEach(a => L.circleMarker([a.latitude, a.longitude], {{
      radius: 6, color: '#fff', weight: 2, fillColor: '#123b57', fillOpacity: 1
    }}).bindTooltip(a.name).addTo(anchorLayer));

    function numericColor(value, config) {{
      const scaled = Number(value || 0) * config.scale;
      let index = config.breaks.findIndex(b => scaled <= b);
      if (index < 0) index = config.colors.length - 1;
      return config.colors[Math.min(index, config.colors.length - 1)];
    }}
    function styleFeature(feature) {{
      const metric = document.getElementById('metric').value;
      const color = metric === 'urban_class'
        ? classColors[feature.properties.urban_class]
        : numericColor(feature.properties[metric], metrics[metric]);
      return {{ color: '#ffffff', weight: .65, fillColor: color, fillOpacity: .76 }};
    }}
    function fmt(value, digits=0) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
      return Number(value).toLocaleString(undefined, {{ maximumFractionDigits: digits }});
    }}
    function showDetails(properties) {{
      document.getElementById('cell-title').textContent = properties.cell_id;
      document.getElementById('cell-class').textContent = properties.urban_class;
      const rows = [
        ['Buildings', fmt(properties.building_count)],
        ['Footprint', fmt(properties.building_footprint_share * 100, 1) + '%'],
        ['POIs / km²', fmt(properties.poi_density_km2, 1)],
        ['Road km / km²', fmt(properties.road_density_km_km2, 1)],
        ['Intersections', fmt(properties.intersection_count)],
        ['Healthcare', fmt(properties.distance_healthcare_m) + ' m'],
        ['Education', fmt(properties.distance_education_m) + ' m'],
        ['Market', fmt(properties.distance_market_m) + ' m']
      ];
      document.getElementById('cell-metrics').innerHTML = rows.map(row =>
        `<div><span>${{row[0]}}</span><strong>${{row[1]}}</strong></div>`).join('');
    }}
    function onEachFeature(feature, layer) {{
      layer.bindTooltip(`<b>${{feature.properties.cell_id}}</b><br>${{feature.properties.urban_class}}`);
      layer.on({{ click: () => showDetails(feature.properties), mouseover: e => e.target.setStyle({{weight: 2, color:'#243b53'}}), mouseout: e => grid.resetStyle(e.target) }});
    }}
    const grid = L.geoJSON(cells, {{ style: styleFeature, onEachFeature }}).addTo(map);
    map.fitBounds(grid.getBounds(), {{ padding: [12, 12] }});

    function updateLegend() {{
      const selected = document.getElementById('metric').value;
      const legend = document.getElementById('legend');
      if (selected === 'urban_class') {{
        legend.innerHTML = Object.entries(classColors).map(([label, color]) =>
          `<div class="legend-row"><i class="swatch" style="background:${{color}}"></i><span>${{label}}</span></div>`).join('');
        return;
      }}
      const config = metrics[selected];
      const starts = [0, ...config.breaks.slice(0, -1)];
      legend.innerHTML = config.colors.map((color, index) => {{
        const upper = index < config.breaks.length ? config.breaks[index] : null;
        const label = upper === null ? `> ${{fmt(config.breaks.at(-1), 1)}}${{config.unit}}` :
          `${{fmt(starts[index], 1)}}–${{fmt(upper, 1)}}${{config.unit}}`;
        return `<div class="legend-row"><i class="swatch" style="background:${{color}}"></i><span>${{label}}</span></div>`;
      }}).join('');
    }}
    document.getElementById('metric').addEventListener('change', () => {{ grid.setStyle(styleFeature); updateLegend(); }});
    L.control.layers(null, {{'Analysis cells': grid, 'Requested anchors': anchorLayer}}, {{position:'topright'}}).addTo(map);
    L.control.scale({{ imperial: false }}).addTo(map);
    updateLegend();
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_urban_atlas_preview(
    cells: gpd.GeoDataFrame,
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Render a four-panel static overview of the atlas foundation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=150)
    for axis in axes.flat:
        axis.set_axis_off()
        axis.set_facecolor("#f7f7f5")

    classes = sorted(cells["urban_class"].unique())
    color_map = {
        label: CLASS_COLORS[index % len(CLASS_COLORS)]
        for index, label in enumerate(classes)
    }
    classified = cells.assign(map_color=cells["urban_class"].map(color_map))
    classified.plot(
        ax=axes[0, 0],
        color=classified["map_color"],
        edgecolor="white",
        linewidth=0.25,
    )
    axes[0, 0].set_title("Exploratory urban-function classes", fontsize=14, fontweight="bold")
    axes[0, 0].legend(
        handles=[
            Line2D([0], [0], marker="s", color="none", markerfacecolor=color_map[label], label=label)
            for label in classes
        ],
        loc="lower left",
        fontsize=7,
        frameon=False,
    )

    panels = [
        (axes[0, 1], "poi_density_km2", "Mapped POI density", "YlOrRd"),
        (axes[1, 0], "building_footprint_share", "Building-footprint share", "Purples"),
        (axes[1, 1], "road_density_km_km2", "Road density", "Blues"),
    ]
    for axis, column, title, color_map_name in panels:
        cells.plot(
            ax=axis,
            column=column,
            cmap=color_map_name,
            edgecolor="white",
            linewidth=0.2,
            legend=True,
            legend_kwds={"shrink": 0.55},
        )
        axis.set_title(title, fontsize=14, fontweight="bold")

    anchors = gpd.GeoDataFrame(
        {"name": [anchor[0] for anchor in area.anchors_lon_lat]},
        geometry=gpd.points_from_xy(
            [anchor[1] for anchor in area.anchors_lon_lat],
            [anchor[2] for anchor in area.anchors_lon_lat],
        ),
        crs="EPSG:4326",
    ).to_crs(cells.crs)
    for axis in axes.flat:
        anchors.plot(
            ax=axis,
            marker="*",
            color="#102a43",
            edgecolor="white",
            linewidth=0.4,
            markersize=80,
            zorder=5,
        )

    figure.suptitle("Dhaka Urban Function Atlas — transparent baseline", fontsize=20, fontweight="bold")
    figure.text(
        0.01,
        0.008,
        "© OpenStreetMap contributors, Overture Maps Foundation | Exploratory mapped structure",
        fontsize=8,
        color="#555555",
    )
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
