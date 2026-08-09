"""Interactive and static maps for Dhaka service accessibility."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

from dhakagraph.config import StudyArea

SERVICE_LABELS = {
    "healthcare": "Healthcare",
    "education": "Education",
    "market": "Markets",
    "park": "Parks",
    "transport": "Transport POIs",
}


def _metric_config(cells: gpd.GeoDataFrame) -> dict[str, Any]:
    metrics: dict[str, tuple[str, str, str]] = {
        "service_desert_score": ("Demand-adjusted service-desert score", "", "high_bad"),
        "service_gap_score": ("Unadjusted service-gap score", "", "high_bad"),
        "built_intensity_proxy": ("Mapped built-intensity proxy", "", "high_good"),
    }
    for group, label in SERVICE_LABELS.items():
        metrics[f"walk_minutes_{group}"] = (f"Walk minutes to nearest {label.lower()}", " min", "high_bad")
        if f"drive_minutes_{group}" in cells:
            metrics[f"drive_minutes_{group}"] = (f"Drive minutes to nearest {label.lower()}", " min", "high_bad")
        for threshold in (10, 15, 30):
            metrics[f"walk_{group}_{threshold}min_count"] = (
                f"{label} reachable in {threshold} walk-minutes",
                "",
                "high_good",
            )

    red = ["#ffffcc", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"]
    blue = ["#f7fbff", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"]
    configuration = {}
    for column, (label, unit, direction) in metrics.items():
        if column not in cells:
            continue
        values = cells[column].replace([np.inf, -np.inf], np.nan).dropna()
        configuration[column] = {
            "label": label,
            "unit": unit,
            "breaks": [
                round(float(value), 3)
                for value in values.quantile([0.2, 0.4, 0.6, 0.8, 0.95]).to_list()
            ] if len(values) else [0, 0, 0, 0, 0],
            "colors": red if direction == "high_bad" else blue,
        }
    return configuration


def build_accessibility_explorer(
    cells: gpd.GeoDataFrame,
    ranking: list[dict[str, Any]],
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Write a switchable network-accessibility and service-desert explorer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    web = cells.to_crs("EPSG:4326").copy()
    web.geometry = web.geometry.simplify(0.00001, preserve_topology=True)
    wanted = [
        "cell_id", "urban_class", "service_desert_score", "service_gap_score",
        "built_intensity_proxy", "largest_service_gap", "geometry",
    ]
    wanted += [column for column in web if column.startswith("walk_minutes_")]
    wanted += [column for column in web if column.startswith("drive_minutes_")]
    wanted += [column for column in web if column.startswith("walk_") and column.endswith("min_count")]
    wanted += [column for column in web if column.startswith("walk_unreachable_")]
    wanted = list(dict.fromkeys(column for column in wanted if column in web))
    geojson = json.loads(web[wanted].to_json(drop_id=True))
    metrics = _metric_config(cells)
    options = "\n".join(
        f"<option value='{column}'>{config['label']}</option>"
        for column, config in metrics.items()
    )
    anchors = [
        {"name": label, "longitude": longitude, "latitude": latitude}
        for label, longitude, latitude in area.anchors_lon_lat
    ]
    top_rows = ranking[:10]

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhaka Service Accessibility</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html,body,#map{{height:100%;margin:0;font-family:Inter,system-ui,sans-serif}} #map{{background:#edf2f4}}
.panel{{position:fixed;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #c8d0d7;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.12)}}
#controls{{left:16px;top:16px;width:min(350px,calc(100vw - 32px));padding:13px 14px}} #details{{left:16px;bottom:24px;width:min(350px,calc(100vw - 32px));padding:12px 14px}}
h1{{font-size:17px;margin:0 0 3px}} .sub,.note{{font-size:12px;color:#4b5563;line-height:1.35}} label{{display:block;font-size:12px;font-weight:650;margin:10px 0 4px}}
select{{width:100%;border:1px solid #aeb8c2;border-radius:6px;padding:7px;background:#fff}} #legend{{margin-top:8px;display:grid;gap:3px;font-size:11px}}
.legend-row{{display:flex;align-items:center;gap:7px}} .swatch{{width:15px;height:11px;border:1px solid rgba(0,0,0,.18)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-top:8px}} .grid span{{display:block;color:#64748b;font-size:10px}} .grid strong{{font-size:13px}}
#ranking{{position:fixed;right:16px;bottom:24px;width:250px;padding:10px 12px;max-height:35vh;overflow:auto}} #ranking ol{{padding-left:22px;margin:7px 0;font-size:11px}} #ranking li{{margin:4px 0}}
@media(max-width:750px){{#details,#ranking{{display:none}}#controls{{max-height:48vh;overflow:auto}}}}
</style></head><body><div id="map"></div>
<section id="controls" class="panel"><h1>Dhaka Service Accessibility</h1>
<div class="sub">Network walking at {summary['walk_speed_km_h']:.1f} km/h · modeled driving · transit not modeled</div>
<label for="metric">Accessibility variable</label><select id="metric">{options}</select><div id="legend"></div>
<div class="note" style="margin-top:9px">Mapped roads and facilities only. Scores do not represent population, service capacity, sidewalk quality or observed trips.</div></section>
<section id="details" class="panel"><strong id="cell-title">Select a cell</strong><div id="cell-class" class="sub">Click a cell to inspect access.</div><div id="cell-metrics" class="grid"></div></section>
<section id="ranking" class="panel"><strong>Highest demand-adjusted gaps</strong><ol>{''.join(f"<li><b>{row['cell_id']}</b> · {row['service_desert_score']:.1f} · {row['largest_service_gap']}</li>" for row in top_rows)}</ol></section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const cells={json.dumps(geojson,separators=(',',':'))}; const metrics={json.dumps(metrics,separators=(',',':'))}; const anchors={json.dumps(anchors,separators=(',',':'))};
const map=L.map('map',{{preferCanvas:true,zoomControl:false}});L.control.zoom({{position:'topright'}}).addTo(map);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:20,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(map);
const anchorLayer=L.layerGroup().addTo(map);anchors.forEach(a=>L.circleMarker([a.latitude,a.longitude],{{radius:6,color:'#fff',weight:2,fillColor:'#123b57',fillOpacity:1}}).bindTooltip(a.name).addTo(anchorLayer));
function fmt(v,d=1){{return v===null||v===undefined||Number.isNaN(Number(v))?'n/a':Number(v).toLocaleString(undefined,{{maximumFractionDigits:d}})}}
function color(v,c){{if(v===null||v===undefined||Number.isNaN(Number(v)))return'#3f3f46';let i=c.breaks.findIndex(b=>Number(v)<=b);if(i<0)i=c.colors.length-1;return c.colors[Math.min(i,c.colors.length-1)]}}
function style(f){{const key=document.getElementById('metric').value;return{{color:'#fff',weight:.65,fillColor:color(f.properties[key],metrics[key]),fillOpacity:.78}}}}
function details(p){{document.getElementById('cell-title').textContent=p.cell_id;document.getElementById('cell-class').textContent=p.urban_class+' · largest gap: '+p.largest_service_gap;
const rows=[['Desert score',fmt(p.service_desert_score)],['Healthcare walk',fmt(p.walk_minutes_healthcare)+' min'],['Education walk',fmt(p.walk_minutes_education)+' min'],['Market walk',fmt(p.walk_minutes_market)+' min'],['Park walk',fmt(p.walk_minutes_park)+' min'],['Healthcare 15m',fmt(p.walk_healthcare_15min_count,0)],['Education 15m',fmt(p.walk_education_15min_count,0)],['Markets 15m',fmt(p.walk_market_15min_count,0)]];
document.getElementById('cell-metrics').innerHTML=rows.map(r=>`<div><span>${{r[0]}}</span><strong>${{r[1]}}</strong></div>`).join('')}}
function each(f,l){{l.bindTooltip(`<b>${{f.properties.cell_id}}</b><br>Service-desert score: ${{fmt(f.properties.service_desert_score)}}`);l.on({{click:()=>details(f.properties),mouseover:e=>e.target.setStyle({{weight:2,color:'#243b53'}}),mouseout:e=>grid.resetStyle(e.target)}})}}
const grid=L.geoJSON(cells,{{style,onEachFeature:each}}).addTo(map);map.fitBounds(grid.getBounds(),{{padding:[12,12]}});
function legend(){{const c=metrics[document.getElementById('metric').value],starts=[0,...c.breaks.slice(0,-1)];document.getElementById('legend').innerHTML=c.colors.map((clr,i)=>{{const upper=i<c.breaks.length?c.breaks[i]:null,label=upper===null?`> ${{fmt(c.breaks.at(-1))}}${{c.unit}}`:`${{fmt(starts[i])}}–${{fmt(upper)}}${{c.unit}}`;return`<div class="legend-row"><i class="swatch" style="background:${{clr}}"></i><span>${{label}}</span></div>`}}).join('')+`<div class="legend-row"><i class="swatch" style="background:#3f3f46"></i><span>Disconnected / no path</span></div>`}}
document.getElementById('metric').addEventListener('change',()=>{{grid.setStyle(style);legend()}});L.control.layers(null,{{'Analysis cells':grid,'Requested anchors':anchorLayer}},{{position:'topright'}}).addTo(map);L.control.scale({{imperial:false}}).addTo(map);legend();
</script></body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_accessibility_preview(
    cells: gpd.GeoDataFrame,
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Render core nearest-service times and the composite gap score."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=150)
    panels = [
        ("walk_minutes_healthcare", "Walk minutes to healthcare", "YlOrRd"),
        ("walk_minutes_education", "Walk minutes to education", "YlOrRd"),
        ("walk_minutes_market", "Walk minutes to market", "YlOrRd"),
        ("service_desert_score", "Demand-adjusted service-desert score", "magma_r"),
    ]
    for axis, (column, title, color_map) in zip(axes.flat, panels, strict=True):
        axis.set_axis_off()
        axis.set_facecolor("#f7f7f5")
        cells.plot(ax=axis,column=column,cmap=color_map,edgecolor="white",linewidth=.2,legend=True,legend_kwds={"shrink":.55})
        axis.set_title(title,fontsize=14,fontweight="bold")
    anchors=gpd.GeoDataFrame({"name":[a[0] for a in area.anchors_lon_lat]},geometry=gpd.points_from_xy([a[1] for a in area.anchors_lon_lat],[a[2] for a in area.anchors_lon_lat]),crs="EPSG:4326").to_crs(cells.crs)
    for axis in axes.flat:
        anchors.plot(ax=axis,marker="*",color="#102a43",edgecolor="white",linewidth=.4,markersize=80,zorder=5)
    figure.suptitle("Dhaka Service Accessibility — modeled network access",fontsize=20,fontweight="bold")
    figure.text(.01,.008,"© OpenStreetMap contributors, Overture Maps Foundation | Not observed travel or service capacity",fontsize=8,color="#555")
    figure.tight_layout(rect=(0, .02, 1, .97))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
