"""Build the City2Graph-style heterogeneous graph view of expanded Dhaka."""

# The embedded JavaScript is intentionally kept close to the Python generator.
# Its long lines are browser code, not project Python API surface.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import mapping

from dhakagraph.config import StudyArea
from dhakagraph.overture import METRIC_CRS

MAX_BUILDINGS = 4_500
MAX_ROAD_EDGES = 14_000
MAX_PUBLIC_NODES = 7_500
MAX_PRIVATE_PRIVATE = 3_000
MAX_PRIVATE_PUBLIC = 1_800


def _json(value: Any) -> str:
    """Serialize compactly while keeping the generated page readable by browsers."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _line_feature(geometry: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": mapping(geometry), "properties": properties}


def _point_feature(point: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(point.x, 6), round(point.y, 6)]},
        "properties": properties,
    }


def _sample_roads(edges: gpd.GeoDataFrame, limit: int = MAX_ROAD_EDGES) -> gpd.GeoDataFrame:
    """Keep important roads and a reproducible spatially broad sample of local roads."""
    edges = edges.loc[edges.geometry.notna() & ~edges.geometry.is_empty].copy()
    if len(edges) <= limit:
        return edges
    road_class = edges.get("class", pd.Series("unclassified", index=edges.index)).fillna(
        "unclassified"
    )
    priority_classes = {"motorway", "trunk", "primary", "secondary"}
    priority = edges.loc[road_class.astype(str).str.lower().isin(priority_classes)]
    priority = priority.sample(frac=1, random_state=42)
    remainder = edges.drop(priority.index)
    remaining = max(limit - len(priority), 0)
    if len(priority) >= limit:
        return priority.head(limit)
    return pd.concat([priority, remainder.sample(n=min(remaining, len(remainder)), random_state=42)])


def _compact_geometry(geometry: Any, tolerance: float = 0.00003) -> Any:
    if geometry.geom_type == "LineString":
        return geometry.simplify(tolerance, preserve_topology=False)
    return geometry.simplify(tolerance, preserve_topology=True)


def _read_buildings(path: Path, cells: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Read and sample Overture footprints for a legible city-scale graph page."""
    buildings = gpd.read_file(path, columns=["id", "class", "geometry"])
    buildings = buildings.loc[buildings.geometry.notna() & ~buildings.geometry.is_empty].copy()
    if len(buildings) > MAX_BUILDINGS:
        buildings = buildings.sample(n=MAX_BUILDINGS, random_state=42)
    buildings = buildings.to_crs(METRIC_CRS)
    buildings["node_id"] = [f"b{i:05d}" for i in range(len(buildings))]
    buildings["representative"] = buildings.geometry.representative_point()
    joined = gpd.sjoin(
        buildings[["node_id", "class", "representative", "geometry"]],
        cells[["cell_id", "geometry"]],
        how="left",
        predicate="within",
    )
    return joined.drop(columns=[column for column in ("index_right",) if column in joined])


def _building_features(buildings: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    features = []
    for _, row in buildings.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(_compact_geometry(row.geometry)),
                "properties": {"node_id": row.node_id, "class": str(row.get("class") or "building")},
            }
        )
    return features


def _road_features(edges: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    features = []
    for _, row in edges.iterrows():
        features.append(
            _line_feature(
                _compact_geometry(row.geometry),
                {
                    "road_class": str(row.get("class") or "unclassified"),
                    "name": str(row.get("names") or "Unnamed road"),
                    "from": int(row.from_node_id),
                    "to": int(row.to_node_id),
                },
            )
        )
    return features


def _cell_features(cells: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    features = []
    for _, row in cells.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(_compact_geometry(row.geometry, 0.00008)),
                "properties": {
                    "cell_id": str(row.cell_id),
                    "urban_class": str(row.get("urban_class") or "unclassified"),
                    "buildings": int(row.get("building_count") or 0),
                    "mapped_area_share": round(float(row.get("building_footprint_share") or 0), 3),
                },
            }
        )
    return features


def _public_nodes(
    nodes: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, limit: int = MAX_PUBLIC_NODES
) -> tuple[list[list[Any]], set[int]]:
    """Choose graph junctions and road endpoints to keep the browser responsive."""
    counts = pd.concat([roads["from_node_id"], roads["to_node_id"]]).value_counts()
    candidates = nodes[nodes.node_id.isin(counts.index)].copy()
    candidates["degree"] = candidates.node_id.map(counts).fillna(0).astype(int)
    if len(candidates) > limit:
        important = candidates.nlargest(min(limit // 3, len(candidates)), "degree")
        rest = candidates.drop(important.index).sample(
            n=min(limit - len(important), len(candidates) - len(important)), random_state=42
        )
        candidates = pd.concat([important, rest])
    node_ids = set(int(value) for value in candidates.node_id)
    points = [
        [round(float(row.geometry.y), 6), round(float(row.geometry.x), 6), int(row.node_id), int(row.degree)]
        for _, row in candidates.iterrows()
    ]
    return points, node_ids


def _private_edges(buildings: gpd.GeoDataFrame) -> list[list[Any]]:
    """Connect nearby sampled building nodes inside each analysis cell."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for _, row in buildings.sort_values("node_id").iterrows():
        cell_id = row.get("cell_id")
        if pd.notna(cell_id):
            grouped[str(cell_id)].append(str(row.node_id))
    pairs: list[list[Any]] = []
    for cell_id in sorted(grouped):
        ids = grouped[cell_id]
        for first, second in zip(ids[::2], ids[1::2], strict=False):
            pairs.append([first, second, cell_id])
            if len(pairs) >= MAX_PRIVATE_PRIVATE:
                return pairs
    return pairs


def _private_public_edges(
    buildings: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame, node_ids: set[int]
) -> list[list[Any]]:
    public = nodes.loc[nodes.node_id.isin(node_ids)].copy()
    if public.empty or buildings.empty:
        return []
    building_sample = buildings.sort_values("node_id").iloc[:: max(len(buildings) // MAX_PRIVATE_PUBLIC, 1)]
    building_sample = building_sample.head(MAX_PRIVATE_PUBLIC)
    tree = cKDTree(np.array([[point.x, point.y] for point in public.geometry]))
    _, positions = tree.query(np.array([[point.x, point.y] for point in building_sample.representative]))
    public_ids = public.node_id.to_numpy()
    return [
        [str(row.node_id), int(public_ids[int(position)])]
        for row, position in zip(building_sample.itertuples(), positions, strict=False)
    ]


def build_city_graph_payload(
    area: StudyArea, processed_dir: Path, raw_dir: Path
) -> dict[str, Any]:
    """Assemble map-ready heterogeneous graph layers from Overture and urban cells."""
    slug = area.slug
    overture_dir = processed_dir / "overture"
    urban_dir = processed_dir / "urban"
    edge_path = overture_dir / f"{slug}_road_edges.geojson"
    node_path = overture_dir / f"{slug}_road_nodes.geojson"
    cells_path = urban_dir / f"{slug}_urban_cells.geojson"
    building_path = raw_dir / "overture" / slug / "2026-07-22.0" / "building.geojson"
    for path in (edge_path, node_path, cells_path, building_path):
        if not path.exists():
            raise FileNotFoundError(f"required graph layer is missing: {path}")

    cells = gpd.read_file(cells_path).to_crs("EPSG:4326")
    roads = gpd.read_file(edge_path).to_crs("EPSG:4326")
    nodes = gpd.read_file(node_path).to_crs(METRIC_CRS)
    roads_metric = roads.to_crs(METRIC_CRS)
    selected_roads = _sample_roads(roads_metric).to_crs("EPSG:4326")
    public_points, public_ids = _public_nodes(nodes.to_crs("EPSG:4326"), roads_metric)
    buildings = _read_buildings(building_path, cells.to_crs(METRIC_CRS))
    buildings_wgs = buildings.to_crs("EPSG:4326")
    buildings_wgs["representative"] = buildings_wgs.geometry.representative_point()
    private_points = [
        [
            round(float(row.representative.y), 6),
            round(float(row.representative.x), 6),
            str(row.node_id),
            str(row.get("cell_id") or "unassigned"),
        ]
        for _, row in buildings_wgs.iterrows()
    ]
    center = [area.center_lat, area.center_lon]
    anchors = [[label, latitude, longitude] for label, longitude, latitude in area.anchors_lon_lat]
    public_edges = selected_roads.loc[
        selected_roads.from_node_id.isin(public_ids) & selected_roads.to_node_id.isin(public_ids)
    ]
    if len(public_edges) > 6_000:
        public_edges = public_edges.sample(n=6_000, random_state=42)

    return {
        "center": center,
        "anchors": anchors,
        "bounds": [[area.geometry.bounds[1], area.geometry.bounds[0]], [area.geometry.bounds[3], area.geometry.bounds[2]]],
        "cells": _feature_collection(_cell_features(cells)),
        "buildings": _feature_collection(_building_features(buildings_wgs)),
        "roads": _feature_collection(_road_features(selected_roads)),
        "public_edges": _feature_collection(_road_features(public_edges)),
        "public_nodes": public_points,
        "private_nodes": private_points,
        "private_edges": _private_edges(buildings),
        "private_public_edges": _private_public_edges(buildings, nodes, public_ids),
        "stats": {
            "cells": len(cells),
            "buildings": len(buildings),
            "road_segments": len(selected_roads),
            "public_nodes": len(public_points),
            "private_nodes": len(private_points),
        },
    }


def _graph_html(payload: dict[str, Any]) -> str:
    data = _json(payload)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Dhaka City Graph Explorer</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="" />
<style>
html, body, #map {{ height: 100%; width: 100%; margin: 0; background: #edf1f2; font-family: Inter, Arial, sans-serif; }}
.panel {{ background: rgba(255,255,255,.94); border: 1px solid #cfd6da; border-radius: 8px; box-shadow: 0 2px 12px rgba(35,48,55,.16); color: #263238; padding: 12px 14px; }}
.title-panel {{ margin: 12px; max-width: 340px; }}
.title-panel h1 {{ font-size: 18px; margin: 0 0 5px; }}
.title-panel p {{ font-size: 12px; line-height: 1.35; margin: 0; color: #526168; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 10px; }}
.stat {{ background: #f1f5f6; border-radius: 5px; padding: 5px; text-align: center; }}
.stat strong {{ display: block; font-size: 14px; color: #18262c; }}
.stat span {{ font-size: 9px; text-transform: uppercase; color: #64747a; }}
.legend {{ min-width: 182px; margin: 12px; }}
.legend h3 {{ font-size: 14px; margin: 0 0 8px; }}
.key {{ display: flex; align-items: center; gap: 8px; font-size: 11px; margin: 5px 0; }}
.swatch {{ display: inline-block; width: 22px; height: 0; border-top: 2px solid #111; }}
.swatch.cell {{ height: 12px; border: 1px solid #8ec7d8; background: #c9e5ec; opacity: .65; }}
.swatch.building {{ height: 10px; border: 1px solid #bbc4ca; background: #dbe0e2; }}
.swatch.red {{ border-color: #e32620; }} .swatch.blue {{ border-color: #1026e8; }}
.swatch.dashed {{ border-top-style: dashed; }}
.leaflet-control-layers {{ border-radius: 7px; }}
.leaflet-popup-content {{ font-size: 12px; line-height: 1.45; }}
.credit {{ font-size: 10px; color: #66757b; margin-top: 8px; }}
</style>
</head>
<body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
const DATA = {data};
const map = L.map('map', {{ preferCanvas: true, zoomControl: true }});
const positron = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 20
}}).addTo(map);
const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap contributors', maxZoom: 20 }});
map.fitBounds(DATA.bounds, {{ padding: [20, 20] }});

function popup(properties) {{
  return Object.entries(properties).map(([key, value]) => `<b>${{key.replaceAll('_',' ')}}</b>: ${{value}}`).join('<br>');
}}
const cells = L.geoJSON(DATA.cells, {{ style: {{ color: '#83bfd0', weight: 0.7, fillColor: '#bfe1e8', fillOpacity: .28 }}, onEachFeature: (f,l) => l.bindPopup(popup(f.properties)) }});
const buildings = L.geoJSON(DATA.buildings, {{ style: {{ color: '#b9c2c7', weight: .35, fillColor: '#d9dfe2', fillOpacity: .34 }}, onEachFeature: (f,l) => l.bindPopup(popup(f.properties)) }});
const streetSegments = L.geoJSON(DATA.roads, {{ style: f => {{ const c = String(f.properties.road_class).toLowerCase(); return {{ color: ['motorway','trunk','primary'].includes(c) ? '#555b5f' : '#777e81', weight: ['motorway','trunk','primary'].includes(c) ? 1.15 : .55, opacity: .72 }}; }}, onEachFeature: (f,l) => l.bindPopup(popup(f.properties)) }});
const publicToPublic = L.geoJSON(DATA.public_edges, {{ style: {{ color: '#1728e8', weight: .8, opacity: .58 }}, onEachFeature: (f,l) => l.bindPopup(popup(f.properties)) }});
const privateToPrivate = L.layerGroup(DATA.private_edges.map(([a,b,cell]) => L.polyline([DATA.private_nodes.find(n => n[2] === a).slice(0,2), DATA.private_nodes.find(n => n[2] === b).slice(0,2)], {{ color: '#e52b26', weight: .75, opacity: .62 }}).bindPopup(`<b>Private-to-private</b><br>cell: ${{cell}}`)));
const publicLookup = Object.fromEntries(DATA.public_nodes.map(n => [String(n[2]), n]));
const privateToPublic = L.layerGroup(DATA.private_public_edges.map(([a,b]) => {{ const p = DATA.private_nodes.find(n => n[2] === a); const q = publicLookup[String(b)]; return p && q ? L.polyline([p.slice(0,2), q.slice(0,2)], {{ color: '#3f43ed', weight: .65, opacity: .45, dashArray: '4 5' }}).bindPopup('<b>Private-to-public</b>') : null; }}).filter(Boolean));
const privateNodes = L.layerGroup(DATA.private_nodes.map(n => L.circleMarker(n.slice(0,2), {{ radius: 2.5, color: '#e52420', fillColor: '#e52420', fillOpacity: .8, weight: .4 }}).bindPopup(`<b>Private node</b><br>building: ${{n[2]}}<br>cell: ${{n[3]}}`)));
const publicNodes = L.layerGroup(DATA.public_nodes.map(n => L.circleMarker(n.slice(0,2), {{ radius: n[3] > 4 ? 3.1 : 2.0, color: '#1428e9', fillColor: '#1428e9', fillOpacity: .82, weight: .4 }}).bindPopup(`<b>Public node</b><br>road node: ${{n[2]}}<br>degree: ${{n[3]}}`)));
const centerPoint = L.marker(DATA.center, {{ title: 'Dhaka study center' }}).bindTooltip('Dhaka study center').bindPopup('<b>Dhaka graph center</b><br>Expanded Overture study area');
const anchorLayer = L.layerGroup(DATA.anchors.map(([label,lat,lon]) => L.circleMarker([lat,lon], {{ radius: 5, color: '#111', fillColor: '#fff', fillOpacity: 1, weight: 1.2 }}).bindTooltip(label)));
cells.addTo(map); buildings.addTo(map); streetSegments.addTo(map); publicToPublic.addTo(map); privateToPrivate.addTo(map); privateToPublic.addTo(map); privateNodes.addTo(map); publicNodes.addTo(map); centerPoint.addTo(map); anchorLayer.addTo(map);
L.control.layers({{ 'CartoDB Positron': positron, 'OpenStreetMap': osm }}, {{ 'Center Point': centerPoint, 'Buildings': buildings, 'Street Segments': streetSegments, 'Tessellation Cells': cells, 'Private Nodes': privateNodes, 'Public Nodes': publicNodes, 'Private-to-Private': privateToPrivate, 'Public-to-Public': publicToPublic, 'Private-to-Public': privateToPublic, 'Dhaka anchors': anchorLayer }}, {{ collapsed: false }}).addTo(map);
const title = L.control({{ position: 'topleft' }}); title.onAdd = () => {{ const d = L.DomUtil.create('div','panel title-panel'); d.innerHTML = `<h1>Dhaka City Graph Explorer</h1><p>A City2Graph-style heterogeneous view of mapped roads, buildings, cells, and cross-layer relationships.</p><div class="stats"><div class="stat"><strong>${{DATA.stats.cells}}</strong><span>cells</span></div><div class="stat"><strong>${{DATA.stats.road_segments.toLocaleString()}}</strong><span>segments</span></div><div class="stat"><strong>${{DATA.stats.buildings.toLocaleString()}}</strong><span>buildings</span></div></div><div class="credit">Mapped Overture features · modeled graph relations · not observed traffic</div>`; return d; }}; title.addTo(map);
const legend = L.control({{ position: 'bottomright' }}); legend.onAdd = () => {{ const d = L.DomUtil.create('div','panel legend'); d.innerHTML = '<h3>Graph layers</h3><div class="key"><i class="swatch cell"></i>Tessellation cells</div><div class="key"><i class="swatch building"></i>Buildings</div><div class="key"><i class="swatch"></i>Street segments</div><div class="key"><i class="swatch red"></i>Private nodes</div><div class="key"><i class="swatch blue"></i>Public nodes</div><div class="key"><i class="swatch red"></i>Private-to-private</div><div class="key"><i class="swatch blue"></i>Public-to-public</div><div class="key"><i class="swatch blue dashed"></i>Private-to-public</div>'; return d; }}; legend.addTo(map);
if (new URLSearchParams(window.location.search).get('thumbnail') === '1') {{
  document.querySelectorAll('.leaflet-control').forEach(element => element.style.display = 'none');
}}
</script></body></html>'''


def build_city_graph_explorer(area: StudyArea, processed_dir: Path, raw_dir: Path, output_path: Path) -> Path:
    """Write the main interactive graph-based Dhaka map."""
    payload = build_city_graph_payload(area, processed_dir, raw_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_graph_html(payload), encoding="utf-8")
    return output_path
