"""Maps for population-weighted service equity."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt

from dhakagraph.config import StudyArea


def build_equity_explorer(
    cells: gpd.GeoDataFrame,
    rankings: list[dict[str, Any]],
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Write an interactive equity-gap explorer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    web = cells.to_crs("EPSG:4326").copy()
    web.geometry = web.geometry.simplify(0.00001, preserve_topology=True)
    metrics = ["equity_gap_mean", "population_share_pct"]
    metrics += [column for column in web if column.startswith("equity_gap_")]
    metrics = list(dict.fromkeys(column for column in metrics if column in web))
    wanted = list(dict.fromkeys(["cell_id", "urban_class", *metrics, "geometry"]))
    geojson = json.loads(web[wanted].to_json(drop_id=True))
    options = "".join(f"<option value='{column}'>{column.replace('_', ' ').title()}</option>" for column in metrics)
    top_rows = rankings[:10]
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhaka Population-Weighted Service Equity</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
html,body,#map{{height:100%;margin:0;font-family:Inter,system-ui,sans-serif}}#map{{background:#edf2f4}}.panel{{position:fixed;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #c8d0d7;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.12)}}#controls{{left:16px;top:16px;width:min(350px,calc(100vw - 32px));padding:13px 14px}}#details{{left:16px;bottom:24px;width:min(350px,calc(100vw - 32px));padding:12px 14px}}#ranking{{right:16px;bottom:24px;width:250px;padding:10px 12px;max-height:35vh;overflow:auto}}h1{{font-size:17px;margin:0 0 3px}}.sub,.note{{font-size:12px;color:#4b5563;line-height:1.35}}label{{display:block;font-size:12px;font-weight:650;margin:10px 0 4px}}select{{width:100%;border:1px solid #aeb8c2;border-radius:6px;padding:7px;background:#fff}}#legend{{margin-top:8px;font-size:11px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-top:8px}}.grid span{{display:block;color:#64748b;font-size:10px}}.grid strong{{font-size:13px}}#ranking ol{{padding-left:22px;margin:7px 0;font-size:11px}}#ranking li{{margin:4px 0}}@media(max-width:750px){{#details,#ranking{{display:none}}#controls{{max-height:48vh;overflow:auto}}}}</style></head><body><div id="map"></div>
<section id="controls" class="panel"><h1>Dhaka Population-Weighted Service Equity</h1><div class="sub">{summary['cell_count']} cells · {summary['population_source']}</div><label for="metric">Equity variable</label><select id="metric">{options}</select><div id="legend"></div><div class="note" style="margin-top:9px">High equity-gap values indicate relatively weaker mapped access under the selected weighting.</div></section>
<section id="details" class="panel"><strong id="cell-title">Select a cell</strong><div id="cell-class" class="sub">Click a cell to inspect its equity profile.</div><div id="cell-metrics" class="grid"></div></section><section id="ranking" class="panel"><strong>Highest equity gaps</strong><ol>{''.join(f"<li><b>{row['cell_id']}</b> · {row['service']} · {row['equity_gap_score']:.1f}</li>" for row in top_rows)}</ol></section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>const cells={json.dumps(geojson,separators=(',',':'))};const map=L.map('map',{{preferCanvas:true,zoomControl:false}});L.control.zoom({{position:'topright'}}).addTo(map);L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:20,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(map);function fmt(v){{return v===null||v===undefined?'n/a':Number(v).toLocaleString(undefined,{{maximumFractionDigits:2}})}}function color(v){{const n=Math.max(0,Math.min(100,Number(v)||0));const c=['#fff5f0','#fee0d2','#fcbba1','#fc9272','#fb6a4a','#de2d26','#a50f15'];return c[Math.min(c.length-1,Math.floor(n/100*c.length))]}}function style(f){{return{{color:'#fff',weight:.65,fillColor:color(f.properties[document.getElementById('metric').value]),fillOpacity:.8}}}}function detail(p){{document.getElementById('cell-title').textContent=p.cell_id;document.getElementById('cell-class').textContent=p.urban_class||'No class';const rows=Object.entries(p).filter(([k])=>k.startsWith('equity_gap_')||k==='population_share_pct').slice(0,6);document.getElementById('cell-metrics').innerHTML=rows.map(r=>`<div><span>${{r[0].replaceAll('_',' ')}}</span><strong>${{fmt(r[1])}}</strong></div>`).join('')}}function each(f,l){{l.bindTooltip(`<b>${{f.properties.cell_id}}</b><br>Gap: ${{fmt(f.properties.equity_gap_mean)}}`);l.on({{click:()=>detail(f.properties),mouseover:e=>e.target.setStyle({{weight:2,color:'#243b53'}}),mouseout:e=>grid.resetStyle(e.target)}})}}const grid=L.geoJSON(cells,{{style,onEachFeature:each}}).addTo(map);map.fitBounds(grid.getBounds(),{{padding:[12,12]}});function update(){{grid.setStyle(style);document.getElementById('legend').textContent='0 = lower gap · 100 = higher gap'}}document.getElementById('metric').addEventListener('change',update);L.control.layers(null,{{'Analysis cells':grid}},{{position:'topright'}}).addTo(map);L.control.scale({{imperial:false}}).addTo(map);update();</script></body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_equity_preview(cells: gpd.GeoDataFrame, output_path: Path) -> Path:
    """Render an equity-gap and population-share preview."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(16, 8), dpi=150)
    for axis, column, title, cmap in zip(
        axes,
        ("equity_gap_mean", "population_share_pct"),
        ("Mean service-equity gap", "Population-weight proxy share"),
        ("OrRd", "Blues"),
        strict=True,
    ):
        axis.set_axis_off()
        cells.plot(ax=axis, column=column, cmap=cmap, edgecolor="white", linewidth=0.2, legend=True, legend_kwds={"shrink": 0.6})
        axis.set_title(title, fontsize=14, fontweight="bold")
    figure.suptitle("Dhaka Population-Weighted Service Equity", fontsize=20, fontweight="bold")
    figure.text(0.01, 0.008, "Population weighting defaults to a mapped built/residential-intensity proxy unless an external cell table is supplied.", fontsize=8, color="#555")
    figure.tight_layout(rect=(0, 0.02, 1, 0.95))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
