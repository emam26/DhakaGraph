"""Command-line pipeline for the first central-Dhaka pilot."""

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
from dhakagraph.config import CENTRAL_DHAKA_PILOT
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
    refresh: bool = False,
    radius: int | None = None,
    samples: int | None = None,
    top_n: int | None = None,
) -> dict[str, Path]:
    """Execute the complete first milestone and return its output paths."""
    area = replace(
        CENTRAL_DHAKA_PILOT,
        radius_m=radius or CENTRAL_DHAKA_PILOT.radius_m,
        centrality_samples=samples or CENTRAL_DHAKA_PILOT.centrality_samples,
        top_n=top_n or CENTRAL_DHAKA_PILOT.top_n,
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
    summary.update(
        {
            "study_area": area.name,
            "center_lat": area.center_lat,
            "center_lon": area.center_lon,
            "radius_m": area.radius_m,
            "centrality_method": "length-weighted sampled node betweenness",
            "centrality_samples": min(area.centrality_samples, analysis_graph.number_of_nodes()),
            "data_attribution": "© OpenStreetMap contributors, ODbL",
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

    summary_path = tables_dir / "network_summary.json"
    ranking_path = tables_dir / "top_intersections.csv"
    map_path = maps_dir / "centrality_map.html"
    preview_path = maps_dir / "centrality_preview.png"
    _write_json(summary_path, summary)
    _write_csv(ranking_path, ranked)
    build_centrality_map(graph, ranked, area, map_path)
    build_static_preview(graph, ranked, area, preview_path)

    return {
        "graph": graph_path,
        "nodes": nodes_path,
        "edges": edges_path,
        "summary": summary_path,
        "ranking": ranking_path,
        "map": map_path,
        "preview": preview_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="redownload OSM data")
    parser.add_argument("--radius", type=int, help="pilot radius in metres")
    parser.add_argument("--centrality-samples", type=int, dest="samples")
    parser.add_argument("--top-n", type=int, help="number of intersections to map")
    return parser


def main() -> None:
    """Run the CLI."""
    args = _parser().parse_args()
    outputs = build_pilot(
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
