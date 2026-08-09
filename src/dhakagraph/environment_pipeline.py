"""CLI pipeline for heat, air, and green-space screening."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from dhakagraph.config import EXPANDED_DHAKA_STUDY
from dhakagraph.environment import build_environmental_screen
from dhakagraph.environment_maps import build_environment_explorer, build_environment_preview


def main() -> None:
    """Build environmental screening outputs."""
    root = Path(__file__).resolve().parents[2]
    source = next((root / "data" / "processed" / "urban").glob("*_service_accessibility.geojson"))
    cells = gpd.read_file(source)
    air_path = root / "data" / "raw" / "urban" / "air_quality.csv"
    cells, rankings, summary = build_environmental_screen(
        cells, air_path if air_path.exists() else None
    )
    summary.update(
        {
            "study_area": EXPANDED_DHAKA_STUDY.name,
            "study_area_slug": EXPANDED_DHAKA_STUDY.slug,
            "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
        }
    )
    maps = root / "outputs" / "maps"
    tables = root / "outputs" / "tables"
    processed = (
        root
        / "data"
        / "processed"
        / "urban"
        / f"{EXPANDED_DHAKA_STUDY.slug}_environmental_screen.geojson"
    )
    cell_table = tables / "environmental_screen_cells.csv"
    ranking_path = tables / "environmental_burden_top.csv"
    summary_path = tables / "environmental_screen_summary.json"
    explorer_path = maps / "environmental_screen.html"
    preview_path = maps / "environmental_screen_preview.png"
    cells.to_crs("EPSG:4326").to_file(processed, driver="GeoJSON")
    cells.drop(columns="geometry").round(6).to_csv(cell_table, index=False)
    pd.DataFrame(rankings).to_csv(ranking_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    build_environment_explorer(cells, rankings, summary, EXPANDED_DHAKA_STUDY, explorer_path)
    build_environment_preview(cells, preview_path)
    print("Environmental screening completed:")
    for path in (explorer_path, preview_path, cell_table, ranking_path, summary_path):
        print(f"  {path}")


if __name__ == "__main__":
    main()
