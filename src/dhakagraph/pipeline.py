"""Command-line pipeline for the Dhaka road-network study."""

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from dhakagraph.analysis import (
    approximate_betweenness,
    graph_summary,
    rank_intersections,
    to_simple_undirected,
)
from dhakagraph.city_graph import build_city_graph_explorer
from dhakagraph.config import STUDY_AREAS
from dhakagraph.explorer import build_network_profile
from dhakagraph.maps import build_centrality_map, build_static_preview
from dhakagraph.osm import city2graph_frames, export_spatial_layers, load_or_download_graph


def project_root() -> Path:
    """Return the repository root from the installed source layout."""
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_pilot(
    *,
    area_key: str = "expanded",
    refresh: bool = False,
    radius: int | None = None,
    samples: int | None = None,
    top_n: int | None = None,
) -> dict[str, Path]:
    """Execute the complete first milestone and return its output paths."""
    if area_key not in STUDY_AREAS:
        choices = ", ".join(sorted(STUDY_AREAS))
        raise ValueError(f"unknown study area {area_key!r}; choose from: {choices}")
    base_area = STUDY_AREAS[area_key]
    if radius is not None and base_area.radius_m is None:
        raise ValueError("--radius can only be used with the Shahbag point-radius area")
    area = replace(
        base_area,
        radius_m=radius or base_area.radius_m,
        centrality_samples=samples or base_area.centrality_samples,
        top_n=top_n or base_area.top_n,
    )
    root = project_root()
    raw_dir = root / "data" / "raw"
    processed_dir = root / "data" / "processed"
    tables_dir = root / "outputs" / "tables"
    maps_dir = root / "outputs" / "maps"

    graph, graph_path = load_or_download_graph(area, raw_dir, refresh=refresh)
    nodes, edges = city2graph_frames(graph)
    nodes_path, edges_path = export_spatial_layers(nodes, edges, processed_dir, area.slug)

    analysis_graph = to_simple_undirected(graph)
    summary = graph_summary(graph, analysis_graph)
    area_summary: dict[str, Any] = {
        "study_area": area.name,
        "study_area_slug": area.slug,
        "selection_method": area.selection_method,
        "center_lat": area.center_lat,
        "center_lon": area.center_lon,
    }
    if area.radius_m is not None:
        area_summary["radius_m"] = area.radius_m
    if area.geometry is not None:
        west, south, east, north = area.geometry.bounds
        area_summary["polygon_bounds_lon_lat"] = [west, south, east, north]
    summary.update(
        area_summary
        | {
            "centrality_method": "length-weighted sampled node betweenness",
            "centrality_samples": min(area.centrality_samples, analysis_graph.number_of_nodes()),
            "data_attribution": "\u00a9 OpenStreetMap contributors, ODbL",
            "city2graph_nodes": len(nodes),
            "city2graph_edges": len(edges),
        }
    )
    scores = approximate_betweenness(
        analysis_graph,
        samples=area.centrality_samples,
        seed=area.random_seed,
    )
    ranked = rank_intersections(analysis_graph, scores, limit=area.top_n)
    profile = build_network_profile(graph, analysis_graph, scores, area)

    summary_path = tables_dir / "network_summary.json"
    ranking_path = tables_dir / "top_intersections.csv"
    profile_path = tables_dir / "network_profile.json"
    map_path = maps_dir / "centrality_map.html"
    explorer_path = maps_dir / "network_explorer.html"
    preview_path = maps_dir / "centrality_preview.png"
    _write_json(summary_path, summary)
    _write_csv(ranking_path, ranked)
    _write_json(profile_path, profile)
    build_centrality_map(graph, ranked, area, map_path)
    build_city_graph_explorer(area, processed_dir, raw_dir, explorer_path)
    build_static_preview(graph, ranked, area, preview_path)

    return {
        "graph": graph_path,
        "nodes": nodes_path,
        "edges": edges_path,
        "summary": summary_path,
        "ranking": ranking_path,
        "profile": profile_path,
        "map": map_path,
        "explorer": explorer_path,
        "preview": preview_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--area",
        choices=sorted(STUDY_AREAS),
        default="expanded",
        help="study area to analyze (default: expanded)",
    )
    parser.add_argument("--refresh", action="store_true", help="redownload OSM data")
    parser.add_argument("--radius", type=int, help="pilot radius in metres")
    parser.add_argument("--centrality-samples", type=int, dest="samples")
    parser.add_argument("--top-n", type=int, help="number of intersections to map")
    return parser


def main() -> None:
    """Run the CLI."""
    args = _parser().parse_args()
    outputs = build_pilot(
        area_key=args.area,
        refresh=args.refresh,
        radius=args.radius,
        samples=args.samples,
        top_n=args.top_n,
    )
    print("DhakaGraph pilot completed:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
