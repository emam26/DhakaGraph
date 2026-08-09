"""CLI pipeline for modeled mobility pressure."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from dhakagraph.config import EXPANDED_DHAKA_STUDY
from dhakagraph.mobility import build_mobility_pressure
from dhakagraph.mobility_maps import build_mobility_explorer, build_mobility_preview


def main() -> None:
    """Build modeled movement-pressure outputs."""
    root = Path(__file__).resolve().parents[2]
    urban_path = next(
        (root / "data" / "processed" / "urban").glob("*_service_accessibility.geojson")
    )
    overture_dir = root / "data" / "processed" / "overture"
    stem = EXPANDED_DHAKA_STUDY.slug
    nodes_path = overture_dir / f"{stem}_road_nodes.geojson"
    edges_path = overture_dir / f"{stem}_road_edges.geojson"
    cells = gpd.read_file(urban_path)
    edges, nodes, rankings, summary = build_mobility_pressure(
        cells, nodes_path, edges_path, EXPANDED_DHAKA_STUDY
    )
    summary["data_attribution"] = "© OpenStreetMap contributors, Overture Maps Foundation"
    maps = root / "outputs" / "maps"
    tables = root / "outputs" / "tables"
    processed_edges = (
        root / "data" / "processed" / "urban" / f"{stem}_mobility_pressure.geojson"
    )
    processed_nodes = (
        root / "data" / "processed" / "urban" / f"{stem}_intersection_pressure.geojson"
    )
    edges.to_crs("EPSG:4326").to_file(processed_edges, driver="GeoJSON")
    nodes.to_crs("EPSG:4326").to_file(processed_nodes, driver="GeoJSON")
    ranking_path = tables / "mobility_pressure_top.csv"
    node_path = tables / "intersection_pressure_top.csv"
    summary_path = tables / "mobility_pressure_summary.json"
    explorer_path = maps / "mobility_pressure.html"
    preview_path = maps / "mobility_pressure_preview.png"
    pd.DataFrame(rankings).to_csv(ranking_path, index=False)
    nodes.nlargest(100, "pressure_score").drop(columns="geometry").to_csv(node_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    build_mobility_explorer(edges, nodes, rankings, summary, EXPANDED_DHAKA_STUDY, explorer_path)
    build_mobility_preview(edges, preview_path)
    print("Modeled mobility pressure completed:")
    for path in (explorer_path, preview_path, ranking_path, node_path, summary_path):
        print(f"  {path}")


if __name__ == "__main__":
    main()
