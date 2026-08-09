"""CLI pipeline for Flood Cascade Simulation (Idea 1)."""

import csv

from dhakagraph.config import EXPANDED_DHAKA_STUDY
from dhakagraph.flood import build_flood_model, export_flood_outputs, project_root
from dhakagraph.flood_maps import build_flood_preview


def main() -> None:
    """Run flood cascade pipeline."""
    root = project_root()
    output_html = root / "outputs" / "maps" / "flood_simulation.html"
    output_json = root / "outputs" / "tables" / "flood_cascade_summary.json"
    output_csv = root / "outputs" / "tables" / "vulnerable_roads.csv"
    output_preview = root / "outputs" / "maps" / "flood_simulation_preview.png"

    print("Running Dhaka Flood Cascade Simulation...")
    model = build_flood_model(EXPANDED_DHAKA_STUDY)
    export_flood_outputs(model, EXPANDED_DHAKA_STUDY, output_html, output_json)
    build_flood_preview(model, output_preview)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if model["vulnerable_edges"]:
        with output_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(model["vulnerable_edges"][0].keys()))
            writer.writeheader()
            writer.writerows(model["vulnerable_edges"])

    print("Flood Simulation complete:")
    print(f"  Map: {output_html}")
    print(f"  Summary: {output_json}")
    print(f"  Vulnerable Roads CSV: {output_csv}")


if __name__ == "__main__":
    main()
