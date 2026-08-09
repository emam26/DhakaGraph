"""Synthesize a multi-risk, multi-access priority screen for Dhaka cells."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from dhakagraph.config import StudyArea
from dhakagraph.flood import estimate_node_elevations
from dhakagraph.overture import METRIC_CRS


def percentile_score(values: pd.Series) -> pd.Series:
    """Convert a numeric signal to a stable 0-100 percentile score."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if numeric.nunique() <= 1:
        return pd.Series(50.0, index=values.index)
    return numeric.rank(method="average", pct=True).mul(100).round(3)


def _pressure_by_cell(cells: gpd.GeoDataFrame, pressure_path: Path) -> pd.DataFrame:
    pressure = gpd.read_file(pressure_path).to_crs(METRIC_CRS)
    pressure = pressure[["pressure_percentile", "geometry"]].copy()
    joined = gpd.sjoin(
        pressure,
        cells[["cell_id", "geometry"]].to_crs(METRIC_CRS),
        how="inner",
        predicate="within",
    )
    if joined.empty:
        return pd.DataFrame(columns=["cell_id", "mobility_pressure_mean", "hot_intersection_count"])
    joined["pressure_percentile"] = pd.to_numeric(
        joined["pressure_percentile"], errors="coerce"
    ).fillna(0.0)
    result = joined.groupby("cell_id").agg(
        mobility_pressure_mean=("pressure_percentile", "mean"),
        mobility_pressure_max=("pressure_percentile", "max"),
        hot_intersection_count=("pressure_percentile", lambda values: int((values >= 75).sum())),
        intersection_pressure_count=("pressure_percentile", "size"),
    )
    return result.reset_index()


def _flood_by_cell(
    cells: gpd.GeoDataFrame, nodes_path: Path, edges_path: Path, water_path: Path
) -> pd.DataFrame:
    nodes = gpd.read_file(nodes_path)
    water = gpd.read_file(water_path)
    elevations = estimate_node_elevations(nodes, water)
    elevation_lookup = dict(zip(nodes["node_id"].astype(str), elevations, strict=True))
    edges = gpd.read_file(edges_path).to_crs(METRIC_CRS)
    edges["min_elevation_m"] = [
        min(
            float(elevation_lookup.get(str(row.from_node_id), 5.0)),
            float(elevation_lookup.get(str(row.to_node_id), 5.0)),
        )
        for row in edges.itertuples()
    ]
    edges["length_m"] = pd.to_numeric(
        edges.get("length", edges.geometry.length), errors="coerce"
    ).fillna(edges.geometry.length)
    centroids = edges[["min_elevation_m", "length_m", "geometry"]].copy()
    centroids.geometry = centroids.geometry.centroid
    joined = gpd.sjoin(
        centroids,
        cells[["cell_id", "geometry"]].to_crs(METRIC_CRS),
        how="inner",
        predicate="within",
    )
    if joined.empty:
        return pd.DataFrame(columns=["cell_id", "flood_2m_edge_share", "flood_3m_edge_share"])
    joined["flood_2m"] = joined["min_elevation_m"] <= 2.0
    joined["flood_3m"] = joined["min_elevation_m"] <= 3.0
    joined["flood_2m_length_m"] = joined["length_m"].where(joined["flood_2m"], 0.0)
    joined["flood_3m_length_m"] = joined["length_m"].where(joined["flood_3m"], 0.0)
    result = joined.groupby("cell_id").agg(
        flood_edge_count=("length_m", "size"),
        flood_2m_edge_count=("flood_2m", "sum"),
        flood_3m_edge_count=("flood_3m", "sum"),
        flood_total_length_m=("length_m", "sum"),
        flood_2m_length_m=("flood_2m_length_m", "sum"),
        flood_3m_length_m=("flood_3m_length_m", "sum"),
    ).reset_index()
    result["flood_2m_edge_share"] = (
        result["flood_2m_edge_count"] / result["flood_edge_count"].clip(lower=1) * 100
    )
    result["flood_3m_edge_share"] = (
        result["flood_3m_edge_count"] / result["flood_edge_count"].clip(lower=1) * 100
    )
    result["flood_2m_length_share"] = (
        result["flood_2m_length_m"] / result["flood_total_length_m"].clip(lower=1) * 100
    )
    result["flood_3m_length_share"] = (
        result["flood_3m_length_m"] / result["flood_total_length_m"].clip(lower=1) * 100
    )
    return result


def build_compound_study(
    cells: gpd.GeoDataFrame,
    equity_table: Path,
    pressure_path: Path,
    nodes_path: Path,
    edges_path: Path,
    water_path: Path,
    area: StudyArea,
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Create a transparent compound-priority score from four mapped signals."""
    result = cells.copy()
    equity = pd.read_csv(equity_table)
    equity_columns = ["cell_id", "population_share_pct", "service_desert_score"]
    result = result.merge(
        equity[equity_columns], on="cell_id", how="left", suffixes=("", "_equity")
    )
    result = result.merge(_pressure_by_cell(result, pressure_path), on="cell_id", how="left")
    result = result.merge(
        _flood_by_cell(result, nodes_path, edges_path, water_path), on="cell_id", how="left"
    )
    numeric_columns = [
        "population_share_pct",
        "service_desert_score",
        "environmental_burden_score",
        "mobility_pressure_mean",
        "flood_2m_length_share",
        "flood_3m_length_share",
    ]
    for column in numeric_columns:
        result[column] = pd.to_numeric(result.get(column, 0), errors="coerce").fillna(0.0)
    result["mobility_pressure_score"] = result["mobility_pressure_mean"].clip(0, 100)
    result["flood_disruption_raw"] = (
        result["flood_2m_length_share"] * 0.7 + result["flood_3m_length_share"] * 0.3
    )
    result["population_proxy_score"] = percentile_score(result["population_share_pct"])
    result["service_need_score"] = percentile_score(result["service_desert_score"])
    result["environmental_burden_score_rank"] = percentile_score(
        result["environmental_burden_score"]
    )
    result["mobility_pressure_score_rank"] = percentile_score(result["mobility_pressure_score"])
    result["flood_disruption_score"] = percentile_score(result["flood_disruption_raw"])
    component_columns = [
        "service_need_score",
        "environmental_burden_score_rank",
        "mobility_pressure_score_rank",
        "flood_disruption_score",
    ]
    result["overlap_count"] = (result[component_columns] >= 75).sum(axis=1)
    result["compound_stress_score"] = result[component_columns].mean(axis=1).round(3)
    result["population_priority_score"] = (
        result["compound_stress_score"] * 0.7 + result["population_proxy_score"] * 0.3
    ).round(3)
    result = result.sort_values(
        ["population_priority_score", "compound_stress_score"], ascending=False
    ).reset_index(drop=True)
    result["priority_rank"] = np.arange(1, len(result) + 1)
    decile_cut = max(math.ceil(len(result) * 0.10), 1)
    quartile_cut = max(math.ceil(len(result) * 0.25), 1)
    result["priority_tier"] = np.select(
        [result["priority_rank"] <= decile_cut, result["priority_rank"] <= quartile_cut],
        ["Very high", "High"],
        default="Screening",
    )
    hotspot_columns = [
        "priority_rank",
        "cell_id",
        "priority_tier",
        "urban_class",
        "population_priority_score",
        "compound_stress_score",
        "overlap_count",
        "population_share_pct",
        "service_need_score",
        "environmental_burden_score_rank",
        "mobility_pressure_score_rank",
        "flood_disruption_score",
        "flood_2m_length_share",
        "flood_3m_length_share",
    ]
    rankings = result[hotspot_columns].head(30).to_dict(orient="records")
    four_way = int((result["overlap_count"] == 4).sum())
    top_decile = result.head(decile_cut)
    summary = {
        "study_area": area.name,
        "study_area_slug": area.slug,
        "cell_count": len(result),
        "priority_definition": (
            "Equal-weight percentile overlap of service need, environmental burden, modeled "
            "intersection pressure, and flood disruption; population proxy used for tie-breaking."
        ),
        "top_decile_cell_count": decile_cut,
        "top_decile_population_proxy_share_pct": round(
            float(top_decile["population_share_pct"].sum()), 2
        ),
        "four_way_overlap_cell_count": four_way,
        "high_overlap_cell_count": int((result["overlap_count"] >= 3).sum()),
        "flood_scenarios_used": ["2.0m", "3.0m"],
        "top_hotspots": rankings[:10],
        "interpretation": (
            "Priority cells are places where multiple mapped or modeled pressures overlap. "
            "They are candidates for field validation and coordinated intervention, not proof "
            "of actual risk, traffic, population, or health outcomes."
        ),
        "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
    }
    return result, rankings, summary
