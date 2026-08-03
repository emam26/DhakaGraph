# ruff: noqa: E501
"""Build a compact, interactive explorer for the expanded Dhaka road graph."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

import folium
import networkx as nx
import osmnx as ox
from branca.element import Element
from folium.plugins import Fullscreen, MeasureControl
from shapely.geometry import LineString

from dhakagraph.config import StudyArea


def _values(value: Any) -> list[str]:
    """Normalize scalar or list-like OSM attributes into readable strings."""
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _street_names(graph: nx.Graph, node_id: Any) -> str:
    names: set[str] = set()
    for _, _, attributes in graph.edges(node_id, data=True):
        names.update(_values(attributes.get("name")))
    return " | ".join(sorted(names))


def _highway_class(attributes: dict[str, Any]) -> str:
    values = _values(attributes.get("highway"))
    return values[0] if values else "unclassified"


def _road_group(attributes: dict[str, Any]) -> str:
    highway = _highway_class(attributes)
    if highway in {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}:
        return "arterial"
    if highway in {"secondary", "secondary_link", "tertiary", "tertiary_link"}:
        return "connector"
    return "local"


def _edge_coordinates(graph: nx.Graph, source: Any, target: Any, attributes: dict[str, Any]) -> list[list[float]]:
    geometry = attributes.get("geometry")
    if geometry is None:
        geometry = LineString(
            [
                (graph.nodes[source]["x"], graph.nodes[source]["y"]),
                (graph.nodes[target]["x"], graph.nodes[target]["y"]),
            ]
        )
    if geometry.geom_type != "LineString":
        geometry = max(geometry.geoms, key=lambda part: part.length)
    geometry = geometry.simplify(0.00002, preserve_topology=False)
    return [[round(x, 5), round(y, 5)] for x, y in geometry.coords]


def _route_edge_coordinates(
    graph: nx.Graph,
    source: Any,
    target: Any,
    attributes: dict[str, Any],
) -> list[list[float]]:
    coordinates = _edge_coordinates(graph, source, target, attributes)
    source_xy = (float(graph.nodes[source]["x"]), float(graph.nodes[source]["y"]))
    first_distance = (coordinates[0][0] - source_xy[0]) ** 2 + (
        coordinates[0][1] - source_xy[1]
    ) ** 2
    last_distance = (coordinates[-1][0] - source_xy[0]) ** 2 + (
        coordinates[-1][1] - source_xy[1]
    ) ** 2
    if last_distance < first_distance:
        coordinates.reverse()
    return [[latitude, longitude] for longitude, latitude in coordinates]


def build_intersection_candidates(
    graph: nx.Graph,
    scores: dict[Any, float],
    *,
    centrality_limit: int = 600,
    degree_limit: int = 300,
) -> list[dict[str, Any]]:
    """Return a compact union of high-centrality and high-degree intersections."""
    centrality_order = sorted(scores, key=lambda node: scores[node], reverse=True)
    degree_order = sorted(graph.nodes, key=lambda node: graph.degree(node), reverse=True)
    candidate_ids = list(
        dict.fromkeys(centrality_order[:centrality_limit] + degree_order[:degree_limit])
    )
    centrality_rank = {node: rank for rank, node in enumerate(centrality_order, start=1)}
    degree_rank = {node: rank for rank, node in enumerate(degree_order, start=1)}

    records: list[dict[str, Any]] = []
    for node_id in candidate_ids:
        attributes = graph.nodes[node_id]
        records.append(
            {
                "node_id": str(node_id),
                "latitude": round(float(attributes["y"]), 7),
                "longitude": round(float(attributes["x"]), 7),
                "betweenness": round(float(scores.get(node_id, 0.0)), 9),
                "centrality_rank": centrality_rank.get(node_id, len(graph)),
                "degree": int(graph.degree(node_id)),
                "degree_rank": degree_rank[node_id],
                "street_names": _street_names(graph, node_id),
            }
        )
    return records


def _nearest_analysis_node(
    original_graph: nx.MultiDiGraph,
    analysis_graph: nx.Graph,
    longitude: float,
    latitude: float,
) -> Any:
    node_id = ox.distance.nearest_nodes(original_graph, longitude, latitude)
    if node_id in analysis_graph:
        return node_id
    return min(
        analysis_graph.nodes,
        key=lambda node: (analysis_graph.nodes[node]["x"] - longitude) ** 2
        + (analysis_graph.nodes[node]["y"] - latitude) ** 2,
    )


def _anchor_route(
    original_graph: nx.MultiDiGraph,
    analysis_graph: nx.Graph,
    area: StudyArea,
) -> dict[str, Any]:
    anchor_lookup = {
        label: {"longitude": longitude, "latitude": latitude}
        for label, longitude, latitude in area.anchors_lon_lat
    }
    preferred_order = [
        label for label in ("Uttara", "Airport", "Mirpur", "Sayedabad") if label in anchor_lookup
    ]
    anchor_nodes = {
        label: _nearest_analysis_node(
            original_graph,
            analysis_graph,
            anchor_lookup[label]["longitude"],
            anchor_lookup[label]["latitude"],
        )
        for label in preferred_order
    }

    segments: list[dict[str, Any]] = []
    total_distance_m = 0.0
    for start_label, end_label in pairwise(preferred_order):
        route = nx.shortest_path(
            analysis_graph,
            anchor_nodes[start_label],
            anchor_nodes[end_label],
            weight="length",
        )
        coordinates: list[list[float]] = []
        distance_m = 0.0
        for source, target in pairwise(route):
            attributes = analysis_graph[source][target]
            distance_m += float(attributes.get("length", 0.0))
            edge_coordinates = _route_edge_coordinates(
                analysis_graph,
                source,
                target,
                attributes,
            )
            if coordinates and edge_coordinates[0] == coordinates[-1]:
                edge_coordinates = edge_coordinates[1:]
            coordinates.extend(edge_coordinates)
        total_distance_m += distance_m
        segments.append(
            {
                "from": start_label,
                "to": end_label,
                "distance_km": round(distance_m / 1_000, 2),
                "coordinates": coordinates,
            }
        )
    return {
        "order": preferred_order,
        "distance_km": round(total_distance_m / 1_000, 2),
        "segments": segments,
        "interpretation": "Illustrative shortest-distance graph connection, not navigation advice.",
    }


def build_network_profile(
    original_graph: nx.MultiDiGraph,
    analysis_graph: nx.Graph,
    scores: dict[Any, float],
    area: StudyArea,
) -> dict[str, Any]:
    """Summarize topology, road classes, named streets, and the anchor corridor."""
    degree_counts = Counter(dict(analysis_graph.degree()).values())
    highway_lengths: defaultdict[str, float] = defaultdict(float)
    road_group_lengths: defaultdict[str, float] = defaultdict(float)
    street_lengths: defaultdict[str, float] = defaultdict(float)
    for _, _, attributes in analysis_graph.edges(data=True):
        length_m = float(attributes.get("length", 0.0))
        highway_lengths[_highway_class(attributes)] += length_m
        road_group_lengths[_road_group(attributes)] += length_m
        names = _values(attributes.get("name"))
        for name in names:
            street_lengths[name] += length_m

    positive_scores = sorted(score for score in scores.values() if score > 0)

    def percentile(fraction: float) -> float:
        if not positive_scores:
            return 0.0
        index = round((len(positive_scores) - 1) * fraction)
        return round(float(positive_scores[index]), 9)

    return {
        "degree_distribution": [
            {"degree": degree, "nodes": degree_counts[degree]} for degree in sorted(degree_counts)
        ],
        "centrality_quantiles": {
            "p50_positive": percentile(0.50),
            "p90_positive": percentile(0.90),
            "p99_positive": percentile(0.99),
            "maximum": round(max(scores.values(), default=0.0), 9),
        },
        "road_class_length_km": [
            {"class": highway, "length_km": round(length / 1_000, 2)}
            for highway, length in sorted(
                highway_lengths.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "road_group_length_km": [
            {"group": group, "length_km": round(length / 1_000, 2)}
            for group, length in sorted(
                road_group_lengths.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "top_named_streets": [
            {"street": street, "length_km": round(length / 1_000, 2)}
            for street, length in sorted(
                street_lengths.items(), key=lambda item: item[1], reverse=True
            )[:12]
        ],
        "anchor_route": _anchor_route(original_graph, analysis_graph, area),
    }


def _network_line_groups(graph: nx.Graph) -> dict[str, list[list[list[float]]]]:
    groups: dict[str, list[list[list[float]]]] = {
        "arterial": [],
        "connector": [],
        "local": [],
    }
    for source, target, attributes in graph.edges(data=True):
        groups[_road_group(attributes)].append(
            _edge_coordinates(graph, source, target, attributes)
        )
    return groups


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_network_explorer(
    original_graph: nx.MultiDiGraph,
    analysis_graph: nx.Graph,
    scores: dict[Any, float],
    summary: dict[str, Any],
    profile: dict[str, Any],
    area: StudyArea,
    output_path: Path,
) -> Path:
    """Build the dynamic map, metric explorer, profiles, and anchor corridor view."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates = build_intersection_candidates(analysis_graph, scores)
    road_groups = _network_line_groups(analysis_graph)

    map_object = folium.Map(
        location=list(area.center),
        zoom_start=11,
        tiles=None,
        prefer_canvas=True,
        control_scale=True,
    )
    map_object.get_root().header.add_child(Element("<title>DhakaGraph Network Explorer</title>"))
    folium.TileLayer("CartoDB positron", name="Light basemap", control=True).add_to(map_object)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(map_object)

    styles = {
        "local": {"color": "#718096", "weight": 0.65, "opacity": 0.33},
        "connector": {"color": "#496a81", "weight": 1.25, "opacity": 0.58},
        "arterial": {"color": "#143d59", "weight": 2.35, "opacity": 0.82},
    }
    layer_names = {
        "local": "Local street graph",
        "connector": "Connector road graph",
        "arterial": "Arterial road graph",
    }
    for group in ("local", "connector", "arterial"):
        feature_group = folium.FeatureGroup(name=layer_names[group], show=True)
        folium.GeoJson(
            {"type": "MultiLineString", "coordinates": road_groups[group]},
            style_function=lambda _feature, style=styles[group]: style,
            smooth_factor=1.5,
        ).add_to(feature_group)
        feature_group.add_to(map_object)

    if area.geometry is not None:
        folium.GeoJson(
            area.geometry.__geo_interface__,
            name="Study boundary",
            style_function=lambda _feature: {
                "color": "#167d8d",
                "weight": 2,
                "opacity": 0.9,
                "fillOpacity": 0.02,
                "dashArray": "7 5",
            },
        ).add_to(map_object)

    corridor_layer = folium.FeatureGroup(name="Illustrative anchor corridor", show=True)
    segment_colors = ["#ec6b56", "#f09f3e", "#8f5aa8"]
    for index, segment in enumerate(profile["anchor_route"]["segments"]):
        folium.PolyLine(
            segment["coordinates"],
            color=segment_colors[index % len(segment_colors)],
            weight=5,
            opacity=0.88,
            tooltip=(
                f"{segment['from']} to {segment['to']}: "
                f"{segment['distance_km']:.2f} km structural shortest path"
            ),
        ).add_to(corridor_layer)
    corridor_layer.add_to(map_object)

    anchor_layer = folium.FeatureGroup(name="Requested place anchors", show=True)
    for label, longitude, latitude in area.anchors_lon_lat:
        folium.CircleMarker(
            [latitude, longitude],
            radius=7,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color="#167d8d",
            fill_opacity=1,
            tooltip=label,
            popup=f"Requested study-area anchor: {label}",
        ).add_to(anchor_layer)
    anchor_layer.add_to(map_object)

    nodes = ox.convert.graph_to_gdfs(original_graph, nodes=True, edges=False)
    west, south, east, north = nodes.total_bounds
    map_object.fit_bounds([[south, west], [north, east]])
    Fullscreen(position="topright").add_to(map_object)
    MeasureControl(position="topright", primary_length_unit="kilometers").add_to(map_object)
    folium.LayerControl(position="topright", collapsed=True).add_to(map_object)

    panel_html = """
<section id="dg-explorer" aria-label="Dhaka road-network explorer">
  <header class="dg-header">
    <div>
      <p class="dg-eyebrow">DHAKAGRAPH / OSM + CITY2GRAPH</p>
      <h1>Network explorer</h1>
      <p>Uttara · Mirpur · Gulshan/Badda/Bashundhara · Sayedabad</p>
    </div>
    <button id="dg-collapse" type="button" aria-expanded="true" aria-label="Collapse explorer">−</button>
  </header>
  <div id="dg-panel-body">
    <div class="dg-stats" aria-label="Network summary">
      <div><span>Nodes</span><strong id="dg-stat-nodes"></strong></div>
      <div><span>Links</span><strong id="dg-stat-links"></strong></div>
      <div><span>Road length</span><strong id="dg-stat-length"></strong></div>
    </div>
    <nav class="dg-tabs" aria-label="Explorer views">
      <button type="button" data-tab="explore" aria-selected="true">Explore</button>
      <button type="button" data-tab="profile" aria-selected="false">Profile</button>
      <button type="button" data-tab="corridor" aria-selected="false">Corridor</button>
    </nav>
    <section class="dg-tab" data-panel="explore">
      <label for="dg-metric">Rank and size intersections by</label>
      <select id="dg-metric">
        <option value="betweenness">Structural betweenness</option>
        <option value="degree">Connected-road degree</option>
      </select>
      <label for="dg-limit">Show top <strong id="dg-limit-value">75</strong> candidates</label>
      <input id="dg-limit" type="range" min="10" max="250" step="5" value="75">
      <label for="dg-search">Filter candidate street names</label>
      <input id="dg-search" type="search" placeholder="e.g. Mirpur or Airport Road">
      <p class="dg-result-line"><strong id="dg-visible-count">0</strong> intersections displayed</p>
      <div id="dg-selected" class="dg-selected" aria-live="polite">
        <p>Select an intersection on the map or in the ranking.</p>
      </div>
      <div id="dg-ranking" class="dg-ranking" aria-label="Visible intersection ranking"></div>
    </section>
    <section class="dg-tab" data-panel="profile" hidden>
      <h2>Intersection degree</h2>
      <p class="dg-note">How many road links meet at each simplified graph node.</p>
      <div id="dg-degree-chart" class="dg-bars"></div>
      <h2>Road network composition</h2>
      <div id="dg-road-chart" class="dg-bars"></div>
      <h2>Longest named road records</h2>
      <div id="dg-street-chart" class="dg-bars"></div>
    </section>
    <section class="dg-tab" data-panel="corridor" hidden>
      <h2>Anchor-to-anchor graph connection</h2>
      <p class="dg-route-total"><strong id="dg-route-total"></strong> combined</p>
      <div id="dg-route-steps"></div>
      <div class="dg-anchor-actions" id="dg-anchor-actions"></div>
      <p class="dg-note">Illustrative shortest-distance graph connection only—not navigation or observed travel time.</p>
    </section>
    <footer>Structural network measures · not live traffic<br>© OpenStreetMap contributors, ODbL</footer>
  </div>
</section>
"""
    css = """
<style>
  :root { --dg-ink:#0c1b2a; --dg-muted:#607384; --dg-panel:rgba(250,252,253,.96); --dg-line:#d8e1e7; --dg-teal:#167d8d; --dg-coral:#e65f4a; --dg-amber:#dd8b22; }
  #dg-explorer { position:fixed; z-index:1000; top:16px; left:16px; width:min(390px,calc(100% - 88px)); max-height:calc(100% - 32px); overflow:auto; box-sizing:border-box; border-radius:18px; background:var(--dg-panel); color:var(--dg-ink); box-shadow:0 18px 50px rgba(12,27,42,.24); backdrop-filter:blur(12px); font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
  #dg-explorer * { box-sizing:border-box; }
  .dg-header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:18px 18px 14px; background:linear-gradient(135deg,#0c3041,#126b78); color:#fff; border-radius:18px 18px 0 0; }
  .dg-header h1 { margin:2px 0 3px; font-size:24px; line-height:1.05; font-weight:700; letter-spacing:-.02em; }
  .dg-header p { margin:0; font-size:12px; opacity:.88; }
  .dg-header .dg-eyebrow { font-size:9px; letter-spacing:.14em; opacity:.7; }
  #dg-collapse { width:32px; height:32px; border:1px solid rgba(255,255,255,.35); border-radius:10px; background:rgba(255,255,255,.1); color:#fff; font-size:20px; cursor:pointer; }
  #dg-panel-body { padding:14px 16px 16px; }
  #dg-explorer.dg-collapsed { width:auto; overflow:hidden; }
  #dg-explorer.dg-collapsed #dg-panel-body, #dg-explorer.dg-collapsed .dg-header > div { display:none; }
  #dg-explorer.dg-collapsed .dg-header { padding:8px; border-radius:14px; }
  .dg-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:13px; }
  .dg-stats div { padding:9px 8px; border:1px solid var(--dg-line); border-radius:12px; background:rgba(255,255,255,.72); }
  .dg-stats span { display:block; color:var(--dg-muted); font-size:10px; text-transform:uppercase; letter-spacing:.06em; }
  .dg-stats strong { display:block; margin-top:3px; font-size:15px; }
  .dg-tabs { display:grid; grid-template-columns:repeat(3,1fr); padding:3px; margin-bottom:13px; border-radius:11px; background:#eaf0f3; }
  .dg-tabs button { border:0; border-radius:8px; padding:7px 8px; background:transparent; color:var(--dg-muted); font-weight:650; cursor:pointer; }
  .dg-tabs button[aria-selected="true"] { background:#fff; color:var(--dg-ink); box-shadow:0 2px 8px rgba(12,27,42,.09); }
  .dg-tab label { display:block; margin:10px 0 5px; color:var(--dg-muted); font-size:11px; font-weight:650; }
  .dg-tab select, .dg-tab input[type="search"] { width:100%; border:1px solid #c8d4dc; border-radius:9px; padding:9px 10px; background:#fff; color:var(--dg-ink); font:inherit; }
  .dg-tab input[type="range"] { width:100%; accent-color:var(--dg-teal); }
  .dg-result-line, .dg-note { margin:9px 0; color:var(--dg-muted); font-size:11px; line-height:1.45; }
  .dg-selected { min-height:72px; padding:11px; margin:10px 0; border-left:4px solid var(--dg-coral); border-radius:4px 10px 10px 4px; background:#fff4f0; }
  .dg-selected p { margin:0; font-size:12px; line-height:1.45; }
  .dg-selected strong { font-size:14px; }
  .dg-selected .dg-coords { color:var(--dg-muted); font-size:10px; }
  .dg-ego { display:block; width:100%; height:76px; margin-top:6px; }
  .dg-ranking { display:grid; gap:5px; }
  .dg-rank-row { display:grid; grid-template-columns:28px 1fr auto; align-items:center; gap:8px; width:100%; border:0; border-radius:9px; padding:7px 8px; background:transparent; color:var(--dg-ink); text-align:left; cursor:pointer; }
  .dg-rank-row:hover, .dg-rank-row:focus { background:#eaf3f4; }
  .dg-rank-row .dg-rank { color:var(--dg-teal); font-weight:750; }
  .dg-rank-row .dg-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }
  .dg-rank-row .dg-value { color:var(--dg-muted); font-size:10px; }
  .dg-tab h2 { margin:14px 0 3px; font-size:14px; }
  .dg-bars { display:grid; gap:7px; margin:8px 0 14px; }
  .dg-bar-row { display:grid; grid-template-columns:minmax(78px,1fr) 2fr auto; align-items:center; gap:7px; font-size:10px; }
  .dg-bar-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dg-bar-track { height:7px; border-radius:99px; overflow:hidden; background:#e4ebef; }
  .dg-bar-fill { height:100%; border-radius:inherit; background:var(--dg-teal); }
  .dg-bar-value { min-width:48px; text-align:right; color:var(--dg-muted); }
  .dg-route-total { margin:5px 0 12px; color:var(--dg-muted); }
  .dg-route-step { display:grid; grid-template-columns:14px 1fr auto; gap:8px; align-items:center; width:100%; border:0; border-radius:10px; padding:9px; margin-bottom:6px; background:#eef4f6; color:var(--dg-ink); text-align:left; cursor:pointer; }
  .dg-route-dot { width:10px; height:10px; border-radius:50%; background:var(--dg-coral); }
  .dg-route-step span:last-child { color:var(--dg-muted); font-size:10px; }
  .dg-anchor-actions { display:flex; flex-wrap:wrap; gap:6px; margin:12px 0; }
  .dg-anchor-actions button { border:1px solid #b9cbd3; border-radius:99px; padding:6px 9px; background:#fff; color:var(--dg-ink); font-size:10px; cursor:pointer; }
  #dg-explorer footer { margin-top:14px; padding-top:10px; border-top:1px solid var(--dg-line); color:var(--dg-muted); font-size:9px; line-height:1.5; }
  .leaflet-control-layers { border:0 !important; border-radius:12px !important; box-shadow:0 8px 24px rgba(12,27,42,.17) !important; }
  @media (max-width:640px) {
    #dg-explorer { top:auto; bottom:10px; left:10px; width:calc(100% - 20px); max-height:52%; border-radius:16px; }
    .dg-header { padding:12px 14px 10px; border-radius:16px 16px 0 0; }
    .dg-header h1 { font-size:19px; }
    #dg-panel-body { padding:10px 12px 12px; }
    .dg-stats div { padding:6px; }
  }
</style>
"""
    payload = {
        "summary": summary,
        "profile": profile,
        "candidates": candidates,
        "anchors": [
            {"label": label, "longitude": longitude, "latitude": latitude}
            for label, longitude, latitude in area.anchors_lon_lat
        ],
    }
    script = """
<script>
window.addEventListener("load", function () {
  const map = window.__MAP_NAME__;
  const data = __PAYLOAD__;
  const root = document.getElementById("dg-explorer");
  const markerLayer = L.layerGroup().addTo(map);
  const selectedLayer = L.layerGroup().addTo(map);
  const nodeRenderer = L.canvas({ padding: .5 });
  const state = { metric: "betweenness", limit: 75, query: "", selected: null };
  const colors = { betweenness: "#e65f4a", degree: "#167d8d" };

  L.DomEvent.disableClickPropagation(root);
  L.DomEvent.disableScrollPropagation(root);
  const formatInteger = value => Number(value).toLocaleString();
  const escapeHtml = value => String(value || "").replace(/[&<>\"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#039;"}[char]));
  const streetLabel = node => node.street_names || "Unnamed connected roads";
  const metricValue = node => state.metric === "betweenness" ? node.betweenness : node.degree;
  const metricRank = node => state.metric === "betweenness" ? node.centrality_rank : node.degree_rank;
  const metricText = node => state.metric === "betweenness" ? node.betweenness.toFixed(5) : `${node.degree} links`;

  document.getElementById("dg-stat-nodes").textContent = formatInteger(data.summary.analysis_nodes);
  document.getElementById("dg-stat-links").textContent = formatInteger(data.summary.analysis_undirected_edges);
  document.getElementById("dg-stat-length").textContent = `${formatInteger(Math.round(data.summary.structural_road_length_km))} km`;

  function egoDiagram(node) {
    const spokes = Math.min(node.degree, 12);
    const lines = [];
    for (let index = 0; index < spokes; index += 1) {
      const angle = (Math.PI * 2 * index / spokes) - Math.PI / 2;
      const x = 140 + Math.cos(angle) * 54;
      const y = 38 + Math.sin(angle) * 29;
      lines.push(`<line x1="140" y1="38" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#78909c" stroke-width="2"/>`);
    }
    return `<svg class="dg-ego" viewBox="0 0 280 76" role="img" aria-label="Topological sketch with ${node.degree} incident links">${lines.join("")}<circle cx="140" cy="38" r="11" fill="${colors[state.metric]}" stroke="#fff" stroke-width="3"/><text x="140" y="42" text-anchor="middle" fill="#fff" font-size="10" font-weight="700">${node.degree}</text></svg>`;
  }

  function selectNode(node, pan = true) {
    state.selected = node.node_id;
    selectedLayer.clearLayers();
    L.circleMarker([node.latitude, node.longitude], { radius: 14, color: "#0c1b2a", weight: 2, fillColor: colors[state.metric], fillOpacity: .35 }).addTo(selectedLayer);
    if (pan) map.panTo([node.latitude, node.longitude]);
    document.getElementById("dg-selected").innerHTML = `<p><strong>#${metricRank(node)} · ${escapeHtml(streetLabel(node))}</strong><br>${state.metric === "betweenness" ? `Betweenness ${node.betweenness.toFixed(6)}` : `${node.degree} connected graph links`} · other rank #${state.metric === "betweenness" ? node.degree_rank : node.centrality_rank}<br><span class="dg-coords">${node.latitude.toFixed(5)}, ${node.longitude.toFixed(5)} · OSM node ${escapeHtml(node.node_id)}</span></p>${egoDiagram(node)}`;
  }

  function visibleCandidates() {
    const query = state.query.trim().toLocaleLowerCase();
    return data.candidates
      .filter(node => !query || streetLabel(node).toLocaleLowerCase().includes(query))
      .sort((left, right) => metricValue(right) - metricValue(left))
      .slice(0, state.limit);
  }

  function renderRanking(nodes) {
    const container = document.getElementById("dg-ranking");
    container.innerHTML = "";
    nodes.slice(0, 10).forEach(node => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "dg-rank-row";
      button.innerHTML = `<span class="dg-rank">${metricRank(node)}</span><span class="dg-name">${escapeHtml(streetLabel(node))}</span><span class="dg-value">${escapeHtml(metricText(node))}</span>`;
      button.addEventListener("click", () => selectNode(node));
      container.appendChild(button);
    });
  }

  function renderNodes() {
    markerLayer.clearLayers();
    selectedLayer.clearLayers();
    const nodes = visibleCandidates();
    const maximum = Math.max(...nodes.map(metricValue), 1e-12);
    nodes.forEach(node => {
      const ratio = metricValue(node) / maximum;
      const marker = L.circleMarker([node.latitude, node.longitude], {
        renderer: nodeRenderer, radius: 3.5 + 8 * Math.sqrt(ratio), color: "#ffffff", weight: 1,
        fillColor: colors[state.metric], fillOpacity: .78
      });
      marker.bindTooltip(`<strong>#${metricRank(node)} ${escapeHtml(streetLabel(node))}</strong><br>${escapeHtml(metricText(node))} · degree ${node.degree}`);
      marker.on("click", () => selectNode(node, false));
      marker.addTo(markerLayer);
    });
    document.getElementById("dg-visible-count").textContent = formatInteger(nodes.length);
    renderRanking(nodes);
    const selected = nodes.find(node => node.node_id === state.selected);
    if (selected) selectNode(selected, false);
  }

  function renderBars(containerId, rows, labelKey, valueKey, formatter, color) {
    const container = document.getElementById(containerId);
    const maximum = Math.max(...rows.map(row => Number(row[valueKey])), 1);
    container.innerHTML = rows.map(row => `<div class="dg-bar-row"><span class="dg-bar-label">${escapeHtml(row[labelKey])}</span><span class="dg-bar-track"><span class="dg-bar-fill" style="width:${(100 * Number(row[valueKey]) / maximum).toFixed(1)}%;background:${color}"></span></span><span class="dg-bar-value">${escapeHtml(formatter(row[valueKey]))}</span></div>`).join("");
  }

  const degrees = data.profile.degree_distribution.filter(row => row.degree > 0 && row.degree <= 8);
  renderBars("dg-degree-chart", degrees, "degree", "nodes", value => formatInteger(value), "#167d8d");
  renderBars("dg-road-chart", data.profile.road_group_length_km, "group", "length_km", value => `${Number(value).toFixed(0)} km`, "#dd8b22");
  renderBars("dg-street-chart", data.profile.top_named_streets.slice(0, 8), "street", "length_km", value => `${Number(value).toFixed(1)} km`, "#8f5aa8");

  document.getElementById("dg-route-total").textContent = `${data.profile.anchor_route.distance_km.toFixed(2)} km`;
  const routeSteps = document.getElementById("dg-route-steps");
  data.profile.anchor_route.segments.forEach((segment, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dg-route-step";
    button.innerHTML = `<span class="dg-route-dot" style="background:${["#ec6b56","#f09f3e","#8f5aa8"][index % 3]}"></span><strong>${escapeHtml(segment.from)} → ${escapeHtml(segment.to)}</strong><span>${segment.distance_km.toFixed(2)} km</span>`;
    button.addEventListener("click", () => map.fitBounds(L.latLngBounds(segment.coordinates), { padding: [28, 28] }));
    routeSteps.appendChild(button);
  });

  const anchorActions = document.getElementById("dg-anchor-actions");
  data.anchors.forEach(anchor => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Focus ${anchor.label}`;
    button.addEventListener("click", () => map.setView([anchor.latitude, anchor.longitude], 14));
    anchorActions.appendChild(button);
  });

  document.getElementById("dg-metric").addEventListener("change", event => { state.metric = event.target.value; renderNodes(); });
  document.getElementById("dg-limit").addEventListener("input", event => { state.limit = Number(event.target.value); document.getElementById("dg-limit-value").textContent = state.limit; renderNodes(); });
  document.getElementById("dg-search").addEventListener("input", event => { state.query = event.target.value; renderNodes(); });
  document.getElementById("dg-collapse").addEventListener("click", event => {
    const collapsed = root.classList.toggle("dg-collapsed");
    event.currentTarget.textContent = collapsed ? "+" : "−";
    event.currentTarget.setAttribute("aria-expanded", String(!collapsed));
    event.currentTarget.setAttribute("aria-label", collapsed ? "Expand explorer" : "Collapse explorer");
  });
  document.querySelectorAll(".dg-tabs button").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll(".dg-tabs button").forEach(item => item.setAttribute("aria-selected", String(item === button)));
    document.querySelectorAll(".dg-tab").forEach(panel => { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
  }));
  renderNodes();
});
</script>
"""
    script = script.replace("__MAP_NAME__", map_object.get_name()).replace(
        "__PAYLOAD__", _compact_json(payload)
    )
    map_object.get_root().html.add_child(Element(css + panel_html + script))
    map_object.save(output_path)
    rendered_html = output_path.read_text(encoding="utf-8")
    normalized_html = "\n".join(line.rstrip() for line in rendered_html.splitlines()) + "\n"
    output_path.write_text(normalized_html, encoding="utf-8")
    return output_path
