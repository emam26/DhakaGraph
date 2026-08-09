"""Interactive and static maps for compound Dhaka urban-stress screening."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt


def build_compound_explorer(
    cells: gpd.GeoDataFrame, rankings: list[dict[str, Any]], summary: dict[str, Any], output_path: Path
) -> Path:
    """Write a switchable compound-priority map."""
    web = cells.to_crs("EPSG:4326").copy()
    web.geometry = web.geometry.simplify(0.00001, preserve_topology=True)
    metrics = [
        "population_priority_score",
        "compound_stress_score",
        "overlap_count",
        "service_need_score",
        "environmental_burden_score_rank",
        "mobility_pressure_score_rank",
        "flood_disruption_score",
    ]
    wanted = ["cell_id", "urban_class", "priority_rank", "priority_tier", *metrics, "geometry"]
    geojson = json.loads(web[wanted].to_json(drop_id=True))
    options = "".join(
        f"<option value='{column}'>{column.replace('_', ' ').title()}</option>" for column in metrics
    )
    top_rows = rankings[:10]
    rows = "".join(
        f"<li><b>{row['cell_id']}</b> · {row['priority_tier']} · {row['population_priority_score']:.1f}</li>"
        for row in top_rows
    )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dhaka Compound Urban Stress</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
html,body,#map{{height:100%;margin:0;font-family:Inter,system-ui,sans-serif}}#map{{background:#edf2f4}}.panel{{position:fixed;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #c8d0d7;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.12)}}#controls{{left:16px;top:16px;width:min(365px,calc(100vw - 32px));padding:13px 14px}}#details{{left:16px;bottom:24px;width:min(365px,calc(100vw - 32px));padding:12px 14px}}#ranking{{right:16px;bottom:24px;width:260px;padding:10px 12px;max-height:38vh;overflow:auto}}h1{{font-size:17px;margin:0 0 3px}}.sub,.note{{font-size:12px;color:#4b5563;line-height:1.35}}label{{display:block;font-size:12px;font-weight:650;margin:10px 0 4px}}select{{width:100%;border:1px solid #aeb8c2;border-radius:6px;padding:7px;background:#fff}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-top:8px}}.grid span{{display:block;color:#64748b;font-size:10px}}.grid strong{{font-size:13px}}#ranking ol{{padding-left:22px;margin:7px 0;font-size:11px}}#ranking li{{margin:4px 0}}@media(max-width:750px){{#details,#ranking{{display:none}}#controls{{max-height:52vh;overflow:auto}}}}</style></head><body><div id="map"></div><section id="controls" class="panel"><h1>Dhaka Compound Urban-Stress Screen</h1><div class="sub">{summary['cell_count']} cells · four mapped/modelled signals</div><label for="metric">Priority variable</label><select id="metric">{options}</select><div class="note" style="margin-top:9px">Higher values indicate stronger overlap of mapped pressure signals. Use this as a field-validation shortlist.</div></section><section id="details" class="panel"><strong id="cell-title">Select a cell</strong><div id="cell-class" class="sub">Click a cell to inspect its compound profile.</div><div id="cell-metrics" class="grid"></div></section><section id="ranking" class="panel"><strong>Highest population-priority cells</strong><ol>{rows}</ol></section><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>const cells={json.dumps(geojson,separators=(',',':'))};const map=L.map('map',{{preferCanvas:true,zoomControl:false}});L.control.zoom({{position:'topright'}}).addTo(map);L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:20,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(map);function fmt(v){{return v===null||v===undefined?'n/a':Number(v).toLocaleString(undefined,{{maximumFractionDigits:2}})}}function color(v){{const n=Math.max(0,Math.min(100,Number(v)||0));const c=['#f7fbff','#deebf7','#c6dbef','#9ecae1','#6baed6','#3182bd','#08519c'];return c[Math.min(c.length-1,Math.floor(n/100*c.length))]}}function style(f){{const p=f.properties;const metric=document.getElementById('metric').value;const value=metric==='overlap_count'?Number(p[metric])*25:Number(p[metric]);return{{color:p.priority_rank<=Math.ceil(cells.features.length*.1)?'#7f1d1d':'#fff',weight:p.priority_rank<=Math.ceil(cells.features.length*.1)?1.3:.55,fillColor:color(value),fillOpacity:.82}}}}function detail(p){{document.getElementById('cell-title').textContent=p.cell_id+' · '+p.priority_tier;document.getElementById('cell-class').textContent=p.urban_class||'No class';const keys=['population_priority_score','compound_stress_score','overlap_count','service_need_score','environmental_burden_score_rank','mobility_pressure_score_rank','flood_disruption_score'];document.getElementById('cell-metrics').innerHTML=keys.map(k=>`<div><span>${{k.replaceAll('_',' ')}}</span><strong>${{fmt(p[k])}}</strong></div>`).join('')}}function each(f,l){{l.bindTooltip(`<b>${{f.properties.cell_id}}</b><br>Priority: ${{fmt(f.properties.population_priority_score)}}`);l.on({{click:()=>detail(f.properties),mouseover:e=>e.target.setStyle({{weight:2,color:'#111827'}}),mouseout:e=>grid.resetStyle(e.target)}})}}const grid=L.geoJSON(cells,{{style,onEachFeature:each}}).addTo(map);map.fitBounds(grid.getBounds(),{{padding:[12,12]}});document.getElementById('metric').addEventListener('change',()=>grid.setStyle(style));L.control.layers(null,{{'Compound cells':grid}},{{position:'topright'}}).addTo(map);L.control.scale({{imperial:false}}).addTo(map);grid.setStyle(style);</script></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_compound_preview(cells: gpd.GeoDataFrame, output_path: Path) -> Path:
    """Render four compact outcome maps for the README and quick review."""
    figure, axes = plt.subplots(2, 2, figsize=(16, 15), dpi=150)
    panels = [
        ("population_priority_score", "Population-priority score", "Blues"),
        ("compound_stress_score", "Compound stress overlap", "YlOrRd"),
        ("overlap_count", "High-signal overlap count", "Reds"),
        ("flood_disruption_score", "Flood-disruption component", "PuBu"),
    ]
    for axis, (column, title, cmap) in zip(axes.flat, panels, strict=True):
        axis.set_axis_off()
        cells.plot(ax=axis, column=column, cmap=cmap, edgecolor="white", linewidth=0.2, legend=True, legend_kwds={"shrink": 0.55})
        axis.set_title(title, fontsize=14, fontweight="bold")
    figure.suptitle("Dhaka Compound Urban-Stress Screening", fontsize=20, fontweight="bold")
    figure.text(0.01, 0.008, "Mapped/modelled screening signals; not observed risk, traffic, population, or health outcomes.", fontsize=8, color="#555")
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
