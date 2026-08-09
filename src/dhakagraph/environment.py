"""Heat, air, and green-space screening analysis for Dhaka."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd


def _percentile(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True).fillna(1.0)


def _optional_air_values(cells: gpd.GeoDataFrame, air_path: Path | None) -> tuple[pd.Series, str]:
    if air_path is not None and air_path.exists():
        air = pd.read_csv(air_path)
        if {"cell_id", "pm25"}.issubset(air.columns):
            values = cells["cell_id"].map(air.set_index("cell_id")["pm25"])
            if values.notna().any():
                return values.fillna(values.median()), f"External cell PM2.5: {air_path.name}"
    road = cells.get("road_density_km_km2", pd.Series(0.0, index=cells.index)).fillna(0)
    building = cells.get("building_density_km2", pd.Series(0.0, index=cells.index)).fillna(0)
    industrial = cells.get("landuse_industrial_share", pd.Series(0.0, index=cells.index)).fillna(0)
    proxy = _percentile(road) * 0.45 + _percentile(building) * 0.35 + _percentile(industrial) * 0.20
    return proxy, "Modeled road/building/industrial exposure proxy; not measured PM2.5"


def build_environmental_screen(
    cells: gpd.GeoDataFrame,
    air_path: Path | None = None,
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Build transparent heat, air-exposure, and green-space screening scores."""
    cells = cells.copy()
    green = cells.get("landuse_green_share", pd.Series(0.0, index=cells.index)).fillna(0)
    park_distance = cells.get("distance_park_m", pd.Series(0.0, index=cells.index)).fillna(0)
    buildings = cells.get("building_footprint_share", pd.Series(0.0, index=cells.index)).fillna(0)
    roads = cells.get("road_density_km_km2", pd.Series(0.0, index=cells.index)).fillna(0)
    density = cells.get("building_density_km2", pd.Series(0.0, index=cells.index)).fillna(0)
    heat = (
        0.45 * _percentile(buildings)
        + 0.25 * _percentile(roads)
        + 0.20 * _percentile(density)
        + 0.10 * (1 - _percentile(green))
    ) * 100
    air_values, air_source = _optional_air_values(cells, air_path)
    air_score = (
        _percentile(air_values) * 100
        if air_source.startswith("External")
        else air_values * 100
    )
    green_deficit = (0.65 * (1 - _percentile(green)) + 0.35 * _percentile(park_distance)) * 100
    cells["heat_exposure_score"] = heat.round(3)
    cells["air_exposure_score"] = air_score.round(3)
    cells["green_deficit_score"] = green_deficit.round(3)
    cells["environmental_burden_score"] = (
        (0.4 * cells["heat_exposure_score"])
        + (0.35 * cells["air_exposure_score"])
        + (0.25 * cells["green_deficit_score"])
    ).round(3)
    rankings: list[dict[str, Any]] = []
    for rank, (_, row) in enumerate(
        cells.nlargest(25, "environmental_burden_score").iterrows(), start=1
    ):
        rankings.append(
            {
                "rank": rank,
                "cell_id": row["cell_id"],
                "environmental_burden_score": float(row["environmental_burden_score"]),
                "heat_exposure_score": float(row["heat_exposure_score"]),
                "air_exposure_score": float(row["air_exposure_score"]),
                "green_deficit_score": float(row["green_deficit_score"]),
                "urban_class": row.get("urban_class", ""),
            }
        )
    summary = {
        "cell_count": len(cells),
        "air_source": air_source,
        "metrics": {
            "heat": "Mapped building/road intensity and low-green-space proxy",
            "air": air_source,
            "green": "Mapped green land-use share and modeled distance to parks",
        },
        "method": "Percentile-normalized transparent environmental screening scores",
        "interpretation": (
            "Scores identify cells with higher modeled environmental burden. They are "
            "not measured temperature, air pollution, or health-risk estimates."
        ),
    }
    return cells, rankings, summary
