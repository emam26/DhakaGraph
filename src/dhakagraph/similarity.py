"""Neighborhood similarity analysis for the Dhaka cell atlas."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from dhakagraph.config import StudyArea

BASE_FEATURES = [
    "building_footprint_share",
    "building_density_km2",
    "road_density_km_km2",
    "intersection_density_km2",
    "poi_density_km2",
    "landuse_residential_share",
    "landuse_commercial_share",
    "landuse_industrial_share",
    "landuse_institutional_share",
    "landuse_green_share",
    "cell_degree_centrality",
    "cell_betweenness_centrality",
    "distance_healthcare_m",
    "distance_education_m",
    "distance_market_m",
    "distance_park_m",
    "distance_transport_m",
    "walk_minutes_healthcare",
    "walk_minutes_education",
    "walk_minutes_market",
    "walk_minutes_park",
    "walk_minutes_transport",
    "service_desert_score",
]


def _nearest_cell(cells: gpd.GeoDataFrame, longitude: float, latitude: float) -> str:
    metric_cells = cells.to_crs("EPSG:32646")
    point = gpd.GeoSeries.from_xy([longitude], [latitude], crs="EPSG:4326").to_crs(
        "EPSG:32646"
    ).iloc[0]
    distances = metric_cells.geometry.representative_point().distance(point)
    return str(cells.loc[distances.idxmin(), "cell_id"])


def build_neighborhood_similarity(
    cells: gpd.GeoDataFrame,
    area: StudyArea,
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Compare every cell with anchor neighborhoods using standardized cosine distance."""
    feature_columns = [column for column in BASE_FEATURES if column in cells]
    if len(feature_columns) < 3:
        raise ValueError("neighborhood similarity requires at least three numeric features")

    values = cells[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    variable = values.loc[:, values.nunique(dropna=False) > 1]
    if variable.shape[1] < 3:
        raise ValueError("neighborhood similarity requires at least three variable features")

    scaler = StandardScaler()
    scaled = scaler.fit_transform(variable)
    component_count = min(12, scaled.shape[0] - 1, scaled.shape[1])
    pca = PCA(n_components=component_count, random_state=area.random_seed)
    embedded = pca.fit_transform(scaled)
    norms = np.linalg.norm(embedded, axis=1, keepdims=True)
    normalized = embedded / np.maximum(norms, 1e-12)

    similarity_columns: dict[str, str] = {}
    rankings: list[dict[str, Any]] = []
    anchor_cells: dict[str, str] = {}
    for anchor_name, longitude, latitude in area.anchors_lon_lat:
        anchor_cell = _nearest_cell(cells, longitude, latitude)
        anchor_cells[anchor_name] = anchor_cell
        anchor_index = cells.index.get_loc(cells.index[cells["cell_id"] == anchor_cell][0])
        distances = cdist(normalized[[anchor_index]], normalized, metric="cosine")[0]
        scores = np.clip((1.0 - distances) * 100.0, 0.0, 100.0)
        column = f"similarity_{anchor_name.lower()}"
        cells[column] = scores.round(3)
        similarity_columns[anchor_name] = column
        ordered = np.argsort(-scores)
        for rank, index in enumerate(ordered[:10], start=1):
            row = cells.iloc[index]
            rankings.append(
                {
                    "anchor": anchor_name,
                    "anchor_cell": anchor_cell,
                    "rank": rank,
                    "cell_id": row["cell_id"],
                    "similarity_score": round(float(scores[index]), 3),
                    "urban_class": row.get("urban_class", ""),
                }
            )

    cells["similarity_mean"] = cells[list(similarity_columns.values())].mean(axis=1).round(3)
    summary = {
        "cell_count": len(cells),
        "anchor_count": len(area.anchors_lon_lat),
        "anchors": list(anchor_cells),
        "anchor_cells": anchor_cells,
        "feature_columns": list(variable.columns),
        "excluded_constant_features": [
            column for column in feature_columns if column not in variable
        ],
        "method": "StandardScaler + PCA + cosine similarity",
        "pca_components": component_count,
        "pca_explained_variance": [
            round(float(value), 4) for value in pca.explained_variance_ratio_
        ],
        "interpretation": (
            "Similarity describes mapped urban structure and modeled service access; "
            "it is not proof that neighborhoods have the same culture, income, or activity."
        ),
    }
    return cells, rankings, summary


def similarity_feature_frame(cells: gpd.GeoDataFrame) -> pd.DataFrame:
    """Return the feature matrix used for audit and testing."""
    columns = [column for column in BASE_FEATURES if column in cells]
    return cells[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
