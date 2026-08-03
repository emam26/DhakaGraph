"""Command-line pipeline for the Dhaka Overture Maps audit."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from dhakagraph.config import STUDY_AREAS
from dhakagraph.overture import (
    OVERTURE_RELEASE,
    OVERTURE_TYPES,
    export_overture_graph_layers,
    layer_audit,
    load_or_download_overture,
    overture_summary,
    process_overture_roads,
)
from dhakagraph.overture_maps import build_overture_explorer, build_overture_preview


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_overture_audit(
    *,
    area_key: str = "expanded",
    release: str = OVERTURE_RELEASE,
    refresh: bool = False,
) -> dict[str, Path]:
    """Download, process, summarize, and visualize Overture data for Dhaka."""
    if area_key not in STUDY_AREAS:
        choices = ", ".join(sorted(STUDY_AREAS))
        raise ValueError(f"unknown study area {area_key!r}; choose from: {choices}")
    area = STUDY_AREAS[area_key]
    root = project_root()
    layers, raw_paths = load_or_download_overture(
        area,
        root / "data" / "raw",
        release=release,
        types=OVERTURE_TYPES,
        refresh=refresh,
    )
    processed_roads, road_nodes, road_edges = process_overture_roads(layers)
    graph_paths = export_overture_graph_layers(
        processed_roads,
        road_nodes,
        road_edges,
        root / "data" / "processed",
        area.slug,
    )
    summary = overture_summary(
        layers,
        processed_roads,
        road_nodes,
        road_edges,
        area,
        release,
    )

    tables_dir = root / "outputs" / "tables"
    maps_dir = root / "outputs" / "maps"
    summary_path = tables_dir / "overture_summary.json"
    audit_path = tables_dir / "overture_layer_audit.csv"
    poi_path = tables_dir / "overture_poi_categories.csv"
    land_use_path = tables_dir / "overture_land_use_classes.csv"
    explorer_path = maps_dir / "overture_explorer.html"
    preview_path = maps_dir / "overture_preview.png"

    _write_json(summary_path, summary)
    _write_csv(audit_path, layer_audit(layers))
    _write_csv(poi_path, summary["top_poi_categories"])
    _write_csv(land_use_path, summary["top_land_use_classes"])
    build_overture_explorer(layers, summary, area, explorer_path)
    build_overture_preview(layers, processed_roads, road_nodes, area, preview_path)

    return {
        **{f"raw_{name}": path for name, path in raw_paths.items()},
        **graph_paths,
        "summary": summary_path,
        "audit": audit_path,
        "poi_categories": poi_path,
        "land_use_classes": land_use_path,
        "explorer": explorer_path,
        "preview": preview_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=sorted(STUDY_AREAS), default="expanded")
    parser.add_argument("--release", default=OVERTURE_RELEASE)
    parser.add_argument("--refresh", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    outputs = build_overture_audit(
        area_key=args.area,
        release=args.release,
        refresh=args.refresh,
    )
    print("DhakaGraph Overture audit completed:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
