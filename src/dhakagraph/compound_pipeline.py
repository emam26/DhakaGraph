"""CLI pipeline for compound urban-stress hotspot screening."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from dhakagraph.compound import build_compound_study
from dhakagraph.compound_maps import build_compound_explorer, build_compound_preview
from dhakagraph.config import EXPANDED_DHAKA_STUDY


def main() -> None:
    """Build compound hotspot outputs from the existing Dhaka study products."""
    root = Path(__file__).resolve().parents[2]
    slug = EXPANDED_DHAKA_STUDY.slug
    urban = root / "data" / "processed" / "urban"
    overture = root / "data" / "processed" / "overture"
    raw_water = root / "data" / "raw" / "overture" / slug / "2026-07-22.0" / "water.geojson"
    cells_path = urban / f"{slug}_environmental_screen.geojson"
    if not cells_path.exists():
        cells_path = urban / f"{slug}_service_accessibility.geojson"
    cells = gpd.read_file(cells_path)
    cells, rankings, summary = build_compound_study(
        cells,
        root / "outputs" / "tables" / "population_equity_cells.csv",
        urban / f"{slug}_intersection_pressure.geojson",
        overture / f"{slug}_road_nodes.geojson",
        overture / f"{slug}_road_edges.geojson",
        raw_water,
        EXPANDED_DHAKA_STUDY,
    )
    maps = root / "outputs" / "maps"
    tables = root / "outputs" / "tables"
    processed = urban / f"{slug}_compound_stress.geojson"
    explorer = maps / "compound_stress.html"
    preview = maps / "compound_stress_preview.png"
    cell_table = tables / "compound_stress_cells.csv"
    hotspot_table = tables / "compound_stress_hotspots.csv"
    summary_path = tables / "compound_stress_summary.json"
    cells.to_crs("EPSG:4326").to_file(processed, driver="GeoJSON")
    cells.drop(columns="geometry").round(6).to_csv(cell_table, index=False)
    pd.DataFrame(rankings).to_csv(hotspot_table, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    build_compound_explorer(cells, rankings, summary, explorer)
    build_compound_preview(cells, preview)
    print("Compound urban-stress screening completed:")
    for path in (explorer, preview, cell_table, hotspot_table, summary_path):
        print(f"  {path}")


if __name__ == "__main__":
    main()
