"""Command-line pipeline for Dhaka's cell-based urban studies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import geopandas as gpd

from dhakagraph.config import STUDY_AREAS
from dhakagraph.overture import (
    OVERTURE_RELEASE,
    export_overture_graph_layers,
    load_or_download_overture,
    process_overture_roads,
)
from dhakagraph.urban import CELL_SIZE_M, build_urban_atlas
from dhakagraph.urban_maps import build_urban_atlas_explorer, build_urban_atlas_preview


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _graph_product_paths(root: Path, slug: str) -> dict[str, Path]:
    base = root / "data" / "processed" / "overture"
    return {
        "roads": base / f"{slug}_processed_roads.geojson",
        "nodes": base / f"{slug}_road_nodes.geojson",
        "edges": base / f"{slug}_road_edges.geojson",
    }


def _load_or_build_graph_products(
    root: Path,
    area_key: str,
    release: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    area = STUDY_AREAS[area_key]
    paths = _graph_product_paths(root, area.slug)
    if all(path.exists() for path in paths.values()):
        return (
            gpd.read_file(paths["roads"]),
            gpd.read_file(paths["nodes"]),
            gpd.read_file(paths["edges"]),
        )

    layers, _ = load_or_download_overture(
        area,
        root / "data" / "raw",
        release=release,
        types=("segment", "connector"),
    )
    roads, nodes, edges = process_overture_roads(layers)
    export_overture_graph_layers(
        roads,
        nodes,
        edges,
        root / "data" / "processed",
        area.slug,
    )
    return roads, nodes, edges


def build_urban_stage_one(
    *,
    area_key: str = "expanded",
    release: str = OVERTURE_RELEASE,
    cell_size_m: int = CELL_SIZE_M,
) -> dict[str, Path]:
    """Build and publish the urban-function atlas foundation."""
    if area_key not in STUDY_AREAS:
        choices = ", ".join(sorted(STUDY_AREAS))
        raise ValueError(f"unknown study area {area_key!r}; choose from: {choices}")
    area = STUDY_AREAS[area_key]
    if area.geometry is None:
        raise ValueError("the urban-function atlas requires a polygon study area")
    root = project_root()
    layers, _ = load_or_download_overture(
        area,
        root / "data" / "raw",
        release=release,
        types=("building", "place", "land_use"),
    )
    roads, road_nodes, road_edges = _load_or_build_graph_products(root, area_key, release)
    cells, contiguity_edges, summary = build_urban_atlas(
        layers,
        roads,
        road_nodes,
        road_edges,
        area,
        cell_size_m=cell_size_m,
    )
    summary["overture_release"] = release

    processed_dir = root / "data" / "processed" / "urban"
    tables_dir = root / "outputs" / "tables"
    maps_dir = root / "outputs" / "maps"
    processed_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    maps_dir.mkdir(parents=True, exist_ok=True)

    cells_path = processed_dir / f"{area.slug}_urban_cells.geojson"
    contiguity_path = processed_dir / f"{area.slug}_cell_contiguity.geojson"
    table_path = tables_dir / "urban_atlas_cells.csv"
    summary_path = tables_dir / "urban_atlas_summary.json"
    explorer_path = maps_dir / "urban_atlas.html"
    preview_path = maps_dir / "urban_atlas_preview.png"

    cells.to_crs("EPSG:4326").to_file(cells_path, driver="GeoJSON")
    contiguity_edges.to_crs("EPSG:4326").reset_index().to_file(
        contiguity_path,
        driver="GeoJSON",
    )
    cells.drop(columns="geometry").round(6).to_csv(table_path, index=False)
    _write_json(summary_path, summary)
    build_urban_atlas_explorer(cells, summary, area, explorer_path)
    build_urban_atlas_preview(cells, area, preview_path)
    return {
        "cells": cells_path,
        "contiguity": contiguity_path,
        "cell_table": table_path,
        "summary": summary_path,
        "explorer": explorer_path,
        "preview": preview_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=sorted(STUDY_AREAS), default="expanded")
    parser.add_argument("--release", default=OVERTURE_RELEASE)
    parser.add_argument("--cell-size", type=int, default=CELL_SIZE_M, dest="cell_size_m")
    return parser


def main() -> None:
    args = _parser().parse_args()
    outputs = build_urban_stage_one(
        area_key=args.area,
        release=args.release,
        cell_size_m=args.cell_size_m,
    )
    print("DhakaGraph urban stage 1 completed:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
