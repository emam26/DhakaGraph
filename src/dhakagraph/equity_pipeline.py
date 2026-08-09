"""CLI pipeline for population-weighted service equity."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from dhakagraph.config import EXPANDED_DHAKA_STUDY
from dhakagraph.equity import build_population_weighted_equity
from dhakagraph.equity_maps import build_equity_explorer, build_equity_preview


def main() -> None:
    """Build population-weighted service equity outputs."""
    root = Path(__file__).resolve().parents[2]
    source = next(
        (root / "data" / "processed" / "urban").glob("*_service_accessibility.geojson")
    )
    cells = gpd.read_file(source)
    population_path = root / "data" / "raw" / "urban" / "population_cell_weights.csv"
    cells, rankings, summary = build_population_weighted_equity(
        cells, population_path if population_path.exists() else None
    )
    summary.update(
        {
            "study_area": EXPANDED_DHAKA_STUDY.name,
            "study_area_slug": EXPANDED_DHAKA_STUDY.slug,
            "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
        }
    )
    output_dir = root / "outputs"
    processed = (
        root
        / "data"
        / "processed"
        / "urban"
        / f"{EXPANDED_DHAKA_STUDY.slug}_population_equity.geojson"
    )
    cells.to_crs("EPSG:4326").to_file(processed, driver="GeoJSON")
    cell_table = output_dir / "tables" / "population_equity_cells.csv"
    rankings_path = output_dir / "tables" / "population_equity_rankings.csv"
    summary_path = output_dir / "tables" / "population_equity_summary.json"
    explorer = output_dir / "maps" / "population_equity.html"
    preview = output_dir / "maps" / "population_equity_preview.png"
    cells.drop(columns="geometry").round(6).to_csv(cell_table, index=False)
    pd.DataFrame(rankings).to_csv(rankings_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    build_equity_explorer(cells, rankings, summary, EXPANDED_DHAKA_STUDY, explorer)
    build_equity_preview(cells, preview)
    print("Population-weighted service equity completed:")
    for path in (explorer, preview, cell_table, rankings_path, summary_path):
        print(f"  {path}")


if __name__ == "__main__":
    main()
