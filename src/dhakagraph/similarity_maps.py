"""Interactive and static maps for neighborhood similarity."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt

from dhakagraph.config import StudyArea


def build_similarity_explorer(
    cells: gpd.GeoDataFrame,
    rankings: list[dict[str, Any]],
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Write a switchable anchor-to-neighborhood similarity explorer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    web = cells.to_crs("EPSG:4326").copy()
    web.geometry = web.geometry.simplify(0.00001, preserve_topology=True)
    similarity_columns = [column for column in web if column.startswith("similarity_")]
    wanted = list(
        dict.fromkeys(["cell_id", "urban_class", "similarity_mean", *similarity_columns, "geometry"])
    )
    geojson = json.loads(web[wanted].to_json(drop_id=True))
    anchors = [
        {"name": label, "longitude": longitude, "latitude": latitude}
        for label, longitude, latitude in area.anchors_lon_lat
    ]
    anchor_columns = {label: f"similarity_{label.lower()}" for label, _, _ in area.anchors_lon_lat}
    top_rows = rankings[:10]
    options = "".join(
        f"<option value='{column}'>{anchor}</option>"
        for anchor, column in anchor_columns.items()
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhaka Neighborhood Similarity</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html,body,#map{{height:100%;margin:0;font-family:Inter,system-ui,sans-serif}}#map{{background:#edf2f4}}
.panel{{position:fixed;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #c8d0d7;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.12)}}
#controls{{left:16px;top:16px;width:min(340px,calc(100vw - 32px));padding:13px 14px}}#details{{left:16px;bottom:24px;width:min(340px,calc(100vw - 32px));padding:12px 14px}}#ranking{{right:16px;bottom:24px;width:250px;padding:10px 12px;max-height:35vh;overflow:auto}}
h1{{font-size:17px;margin:0 0 3px}}.sub,.note{{font-size:12px;color:#4b5563;line-height:1.35}}label{{display:block;font-size:12px;font-weight:650;margin:10px 0 4px}}select{{width:100%;border:1px solid #aeb8c2;border-radius:6px;padding:7px;background:#fff}}
#legend{{margin-top:8px;display:grid;gap:3px;font-size:11px}}.legend-row{{display:flex;align-items:center;gap:7px}}.swatch{{width:15px;height:11px;border:1px solid rgba(0,0,0,.18)}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-top:8px}}.grid span{{display:block;color:#64748b;font-size:10px}}.grid strong{{font-size:13px}}
#ranking ol{{padding-left:22px;margin:7px 0;font-size:11px}}#ranking li{{margin:4px 0}}@media(max-width:750px){{#details,#ranking{{display:none}}#controls{{max-height:48vh;overflow:auto}}}}
</style></head><body><div id="map"></div>
<section id="controls" class="panel"><h1>Dhaka Neighborhood Similarity</h1>
<div class="sub">Compare mapped urban structure and modeled service access across {summary['cell_count']} cells.</div>
<label for="anchor">Reference neighborhood</label><select id="anchor">{options}</select><div id="legend"></div>
<div class="note" style="margin-top:9px">High scores mean the cell has a similar mapped feature profile to the selected anchor.</div></section>
<section id="details" class="panel"><strong id="cell-title">Select a cell</strong><div id="cell-class" class="sub">Click a cell to inspect similarity.</div><div id="cell-metrics" class="grid"></div></section>
<section id="ranking" class="panel"><strong>Top similar cells</strong><ol id="ranking-list"></ol></section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const cells={json.dumps(geojson,separators=(',',':'))};const anchors={json.dumps(anchors,separators=(',',':'))};const rankings={json.dumps(top_rows,separators=(',',':'))};
const map=L.map('map',{{preferCanvas:true,zoomControl:false}});L.control.zoom({{position:'topright'}}).addTo(map);L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:20,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(map);
const anchorLayer=L.layerGroup().addTo(map);anchors.forEach(a=>L.circleMarker([a.latitude,a.longitude],{{radius:6,color:'#fff',weight:2,fillColor:'#123b57',fillOpacity:1}}).bindTooltip(a.name).addTo(anchorLayer));
function fmt(v,d=1){{return v===null||v===undefined||Number.isNaN(Number(v))?'n/a':Number(v).toLocaleString(undefined,{{maximumFractionDigits:d}})}}
function color(v){{if(v===null||v===undefined)return'#64748b';const n=Number(v);const colors=['#f7fbff','#deebf7','#c6dbef','#9ecae1','#6baed6','#3182bd','#08519c'];return colors[Math.max(0,Math.min(colors.length-1,Math.floor(n/100*colors.length)))];}}
function style(f){{const key=document.getElementById('anchor').value;return{{color:'#fff',weight:.65,fillColor:color(f.properties[key]),fillOpacity:.8}}}}
function details(p){{const key=document.getElementById('anchor').value;document.getElementById('cell-title').textContent=p.cell_id;document.getElementById('cell-class').textContent=p.urban_class||'No class';document.getElementById('cell-metrics').innerHTML=[['Similarity',fmt(p[key])+' / 100'],['Mean similarity',fmt(p.similarity_mean)],['Reference',key.replace('similarity_','')]].map(r=>`<div><span>${{r[0]}}</span><strong>${{r[1]}}</strong></div>`).join('')}}
function each(f,l){{l.bindTooltip(`<b>${{f.properties.cell_id}}</b><br>Similarity: ${{fmt(f.properties[document.getElementById('anchor').value])}}`);l.on({{click:()=>details(f.properties),mouseover:e=>e.target.setStyle({{weight:2,color:'#243b53'}}),mouseout:e=>grid.resetStyle(e.target)}})}}
const grid=L.geoJSON(cells,{{style,onEachFeature:each}}).addTo(map);map.fitBounds(grid.getBounds(),{{padding:[12,12]}});
function update(){{grid.setStyle(style);const key=document.getElementById('anchor').value;document.getElementById('legend').innerHTML='<div class="legend-row"><i class="swatch" style="background:#08519c"></i><span>100 = very similar</span></div><div class="legend-row"><i class="swatch" style="background:#f7fbff"></i><span>0 = weak similarity</span></div>';const anchor=key.replace('similarity_','');document.getElementById('ranking-list').innerHTML=rankings.filter(r=>r.anchor===anchor).map(r=>`<li><b>${{r.cell_id}}</b> · ${{fmt(r.similarity_score)}}<br>${{r.urban_class}}</li>`).join('')}}
document.getElementById('anchor').addEventListener('change',update);L.control.layers(null,{{'Analysis cells':grid,'Reference anchors':anchorLayer}},{{position:'topright'}}).addTo(map);L.control.scale({{imperial:false}}).addTo(map);update();
</script></body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_similarity_preview(
    cells: gpd.GeoDataFrame,
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Render four anchor similarity maps for a README-friendly preview."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    anchors = [name for name, _, _ in area.anchors_lon_lat]
    figure, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=150)
    for axis, anchor in zip(axes.flat, anchors[:4], strict=True):
        column = f"similarity_{anchor.lower()}"
        axis.set_axis_off()
        cells.plot(ax=axis, column=column, cmap="Blues", vmin=0, vmax=100, edgecolor="white", linewidth=0.2, legend=True, legend_kwds={"shrink": 0.55})
        axis.set_title(f"Similarity to {anchor}", fontsize=14, fontweight="bold")
    figure.suptitle("Dhaka Neighborhood Similarity", fontsize=20, fontweight="bold")
    figure.text(0.01, 0.008, "Mapped urban structure and modeled service-access features; not social or demographic similarity.", fontsize=8, color="#555")
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
