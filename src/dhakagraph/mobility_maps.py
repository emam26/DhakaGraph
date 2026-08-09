"""Maps for modeled Dhaka mobility pressure."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt

from dhakagraph.config import StudyArea


def build_mobility_explorer(
    edges: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    rankings: list[dict[str, Any]],
    summary: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Write a pressure-scaled road and intersection explorer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    web_edges = edges.to_crs("EPSG:4326").copy().sort_values("pressure_score", ascending=False).head(2500)
    web_edges.geometry = web_edges.geometry.simplify(0.00002, preserve_topology=True)
    edge_geojson = json.loads(web_edges[["pressure_score", "pressure_percentile", "route_count", "road_class", "names", "geometry"]].to_json(drop_id=True))
    web_nodes = nodes.to_crs("EPSG:4326").nlargest(500, "pressure_score")
    node_geojson = json.loads(web_nodes[["pressure_score", "pressure_percentile", "geometry"]].to_json(drop_id=True))
    anchors = [{"name": label, "longitude": lon, "latitude": lat} for label, lon, lat in area.anchors_lon_lat]
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dhaka Modeled Mobility Pressure</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
html,body,#map{{height:100%;margin:0;font-family:Inter,system-ui,sans-serif}}#map{{background:#edf2f4}}.panel{{position:fixed;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #c8d0d7;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.12)}}#controls{{left:16px;top:16px;width:min(350px,calc(100vw - 32px));padding:13px 14px}}#details{{left:16px;bottom:24px;width:min(350px,calc(100vw - 32px));padding:12px 14px}}h1{{font-size:17px;margin:0 0 3px}}.sub,.note{{font-size:12px;color:#4b5563;line-height:1.35}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-top:8px}}.grid span{{display:block;color:#64748b;font-size:10px}}.grid strong{{font-size:13px}}@media(max-width:750px){{#details{{display:none}}#controls{{max-height:48vh;overflow:auto}}}}</style></head><body><div id="map"></div><section id="controls" class="panel"><h1>Dhaka Modeled Mobility Pressure</h1><div class="sub">{summary['routed_pairs']:,} weighted origin-destination routes · top 2,500 pressure edges shown</div><div class="note" style="margin-top:9px">This map estimates potential movement pressure from mapped origins and destinations. It is not observed traffic.</div></section><section id="details" class="panel"><strong id="title">Select a road or intersection</strong><div class="sub" id="sub">Click a line or point to inspect modeled pressure.</div><div class="grid" id="metrics"></div></section><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const edges={json.dumps(edge_geojson,separators=(',',':'))};const nodes={json.dumps(node_geojson,separators=(',',':'))};const anchors={json.dumps(anchors,separators=(',',':'))};const map=L.map('map',{{preferCanvas:true,zoomControl:false}});L.control.zoom({{position:'topright'}}).addTo(map);L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:20,attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(map);function fmt(v){{return Number(v||0).toLocaleString(undefined,{{maximumFractionDigits:2}})}}function edgeStyle(f){{const p=Number(f.properties.pressure_percentile||0);return{{color:'#b2182b',weight:1+5*p/100,opacity:.25+.7*p/100}}}}function show(p,type){{document.getElementById('title').textContent=type==='edge'?(p.names&&p.names!=='nan'?p.names:'Modeled pressure road'):('Intersection '+p.node_id);document.getElementById('sub').textContent='Modeled potential movement';document.getElementById('metrics').innerHTML=[['Pressure score',fmt(p.pressure_score)],['Percentile',fmt(p.pressure_percentile)+'%'],['Routes',p.route_count?fmt(p.route_count):'n/a'],['Road class',p.road_class||'n/a']].map(r=>`<div><span>${{r[0]}}</span><strong>${{r[1]}}</strong></div>`).join('')}}function eachEdge(f,l){{l.bindTooltip('Pressure percentile: '+fmt(f.properties.pressure_percentile)+'%');l.on('click',()=>show(f.properties,'edge'))}}const edgeLayer=L.geoJSON(edges,{{style:edgeStyle,onEachFeature:eachEdge}}).addTo(map);const nodeLayer=L.geoJSON(nodes,{{pointToLayer:(f,ll)=>L.circleMarker(ll,{{radius:3+5*Number(f.properties.pressure_percentile||0)/100,color:'#7f0000',fillColor:'#de2d26',fillOpacity:.75,weight:1}}),onEachFeature:(f,l)=>l.on('click',()=>show(f.properties,'node'))}}).addTo(map);const anchorLayer=L.layerGroup();anchors.forEach(a=>L.circleMarker([a.latitude,a.longitude],{{radius:6,color:'#fff',weight:2,fillColor:'#123b57',fillOpacity:1}}).bindTooltip(a.name).addTo(anchorLayer));map.fitBounds(edgeLayer.getBounds(),{{padding:[12,12]}});L.control.layers({{}},{{'Modeled pressure roads':edgeLayer,'Top intersections':nodeLayer,'Anchors':anchorLayer}},{{position:'topright'}}).addTo(map);L.control.scale({{imperial:false}}).addTo(map);</script></body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_mobility_preview(edges: gpd.GeoDataFrame, output_path: Path) -> Path:
    """Render the network and highest modeled pressure roads."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(12, 12), dpi=150)
    axis.set_axis_off()
    edges.to_crs("EPSG:32646").plot(ax=axis, color="#d9e2ec", linewidth=0.08, alpha=0.35)
    edges.nlargest(4000, "pressure_score").to_crs("EPSG:32646").plot(
        ax=axis, column="pressure_percentile", cmap="magma", linewidth=0.55, alpha=0.85
    )
    axis.set_title("Dhaka Modeled Mobility Pressure", fontsize=20, fontweight="bold")
    figure.text(0.01, 0.008, "Potential origin-destination pressure from mapped buildings and destinations; not observed traffic.", fontsize=8, color="#555")
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
