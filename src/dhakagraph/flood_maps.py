"""Static flood-scenario preview maps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt

from dhakagraph.overture import METRIC_CRS


def build_flood_preview(
    flood_model: dict[str, Any],
    output_path: Path,
) -> Path:
    """Render inundated-road scenarios at four modeled water levels."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for u, v, data in flood_model["base_graph"].edges(data=True):
        geometry = data.get("geometry")
        if geometry is not None and not geometry.is_empty:
            records.append(
                {
                    "node_from": u,
                    "node_to": v,
                    "min_elevation_m": data["min_elevation"],
                    "geometry": geometry,
                }
            )
    edges = gpd.GeoDataFrame(records, geometry="geometry", crs=METRIC_CRS)
    levels = (0.5, 1.5, 2.0, 3.0)
    figure, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=150)
    colors = {0.5: "#FCD34D", 1.5: "#EF4444", 2.0: "#B91C1C", 3.0: "#7F1D1D"}
    for axis, level in zip(axes.flat, levels, strict=True):
        axis.set_axis_off()
        edges.plot(ax=axis, color="#d9e2ec", linewidth=0.15, alpha=0.35)
        inundated = edges.loc[edges["min_elevation_m"] <= level]
        if not inundated.empty:
            inundated.plot(ax=axis, color=colors[level], linewidth=0.55, alpha=0.8)
        axis.set_title(f"Modeled flood level: {level:.1f} m", fontsize=14, fontweight="bold")
    figure.suptitle("Dhaka Flood-Resilience Network Scenarios", fontsize=20, fontweight="bold")
    figure.text(
        0.01,
        0.008,
        "Scenario proxy based on distance-to-water elevation estimates; not observed flood depth.",
        fontsize=8,
        color="#555",
    )
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    figure.savefig(output_path, bbox_inches="tight", facecolor="#f7f7f5")
    plt.close(figure)
    return output_path
