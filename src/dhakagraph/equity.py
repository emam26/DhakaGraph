"""Population-weighted service equity analysis for Dhaka."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

SERVICE_GROUPS = ("healthcare", "education", "market", "park", "transport")


def _percentile(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True).fillna(1.0)


def _population_weights(
    cells: gpd.GeoDataFrame,
    population_path: Path | None,
) -> tuple[pd.Series, str]:
    if population_path is not None and population_path.exists():
        population = pd.read_csv(population_path)
        required = {"cell_id", "population"}
        if not required.issubset(population.columns):
            raise ValueError("population weights must contain cell_id and population columns")
        values = cells["cell_id"].map(population.set_index("cell_id")["population"])
        if values.notna().any() and float(values.fillna(0).sum()) > 0:
            return (
                values.fillna(0).clip(lower=0),
                f"External cell population: {population_path.name}",
            )

    building = cells.get("building_density_km2", pd.Series(0.0, index=cells.index)).fillna(0)
    residential = cells.get(
        "landuse_residential_share", pd.Series(0.0, index=cells.index)
    ).fillna(0)
    footprint = cells.get(
        "building_footprint_share", pd.Series(0.0, index=cells.index)
    ).fillna(0)
    proxy = (np.log1p(building) * (0.5 + residential) * (0.5 + footprint)).clip(lower=0)
    return proxy, "Mapped built/residential-intensity proxy; not census population"


def build_population_weighted_equity(
    cells: gpd.GeoDataFrame,
    population_path: Path | None = None,
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Calculate cell-level service equity and population-weighted summaries."""
    cells = cells.copy()
    population, population_source = _population_weights(cells, population_path)
    cells["population_weight_raw"] = population.round(6)
    total = float(population.sum())
    cells["population_weight"] = (population / total if total else 1.0 / len(cells)).round(8)
    cells["population_share_pct"] = (cells["population_weight"] * 100).round(4)

    rankings: list[dict[str, Any]] = []
    for group in SERVICE_GROUPS:
        time_column = f"walk_minutes_{group}"
        count_column = f"walk_{group}_15min_count"
        if time_column not in cells or count_column not in cells:
            continue
        times = pd.to_numeric(cells[time_column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        counts = pd.to_numeric(cells[count_column], errors="coerce").fillna(0)
        time_bad = _percentile(times.fillna(times.max() if times.notna().any() else 0))
        count_bad = 1.0 - _percentile(counts)
        gap = (0.7 * time_bad + 0.3 * count_bad) * 100
        cells[f"equity_gap_{group}"] = gap.round(3)
        cells[f"population_weighted_{group}_access"] = (
            (times <= 15).astype(float) * cells["population_weight"] * 100
        ).round(6)
        cells[f"population_weighted_{group}_time"] = (
            times.fillna(times.max() if times.notna().any() else 0) * cells["population_weight"]
        ).round(6)
        for index in cells.sort_values(f"equity_gap_{group}", ascending=False).head(10).index:
            row = cells.loc[index]
            rankings.append(
                {
                    "service": group,
                    "rank": len([r for r in rankings if r["service"] == group]) + 1,
                    "cell_id": row["cell_id"],
                    "equity_gap_score": round(float(row[f"equity_gap_{group}"]), 3),
                    "population_share_pct": round(float(row["population_share_pct"]), 4),
                    "walk_minutes": round(float(row[time_column]), 3),
                    "facilities_within_15min": int(row[count_column]),
                    "urban_class": row.get("urban_class", ""),
                }
            )

    gap_columns = [
        f"equity_gap_{group}"
        for group in SERVICE_GROUPS
        if f"equity_gap_{group}" in cells
    ]
    cells["equity_gap_mean"] = cells[gap_columns].mean(axis=1).round(3)
    summaries: dict[str, Any] = {}
    for group in SERVICE_GROUPS:
        time_column = f"walk_minutes_{group}"
        access_column = f"population_weighted_{group}_access"
        if time_column not in cells or access_column not in cells:
            continue
        summaries[group] = {
            "population_weighted_mean_walk_minutes": round(
                float(cells[f"population_weighted_{group}_time"].sum()), 3
            ),
            "population_share_within_15_minutes": round(
                float(cells[access_column].sum()), 3
            ),
            "unweighted_median_walk_minutes": round(float(cells[time_column].median()), 3),
            "p90_walk_minutes": round(float(cells[time_column].quantile(0.9)), 3),
        }
    summary = {
        "cell_count": len(cells),
        "population_weight_total": round(total, 6),
        "population_source": population_source,
        "service_summaries": summaries,
        "method": "Population-weighted nearest walking time and 15-minute access",
        "interpretation": (
            "Equity scores identify cells with relatively weak mapped service access "
            "under the selected population weighting. They do not measure income, "
            "service capacity, quality, or individual outcomes."
        ),
    }
    return cells, rankings, summary
