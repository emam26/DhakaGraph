"""Cell-based urban-function features for the Dhaka case study."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from typing import Any

import city2graph as c2g
import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import box
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from dhakagraph.config import StudyArea
from dhakagraph.overture import METRIC_CRS, poi_group, poi_primary_category

CELL_SIZE_M = 750
CLUSTER_COUNT = 7

POI_COLUMNS = {
    "Healthcare": "poi_healthcare",
    "Education": "poi_education",
    "Food & drink": "poi_food_drink",
    "Retail & markets": "poi_retail_markets",
    "Transport": "poi_transport",
    "Civic & religious": "poi_civic_religious",
    "Recreation & culture": "poi_recreation_culture",
    "Other": "poi_other",
}

LAND_USE_COLUMNS = {
    "residential": "landuse_residential_share",
    "commercial": "landuse_commercial_share",
    "industrial": "landuse_industrial_share",
    "institutional": "landuse_institutional_share",
    "green_recreation": "landuse_green_share",
    "transport": "landuse_transport_share",
    "other": "landuse_other_share",
}

ATLAS_FEATURE_COLUMNS = [
    "building_footprint_share",
    "building_density_km2",
    "road_density_km_km2",
    "intersection_density_km2",
    "poi_density_km2",
    *[f"{column}_density_km2" for column in POI_COLUMNS.values() if column != "poi_other"],
    *[column for group, column in LAND_USE_COLUMNS.items() if group != "other"],
    "cell_degree_centrality",
    "cell_betweenness_centrality",
    "distance_healthcare_m",
    "distance_education_m",
    "distance_market_m",
    "distance_park_m",
    "distance_transport_m",
]


def make_analysis_grid(
    area: StudyArea,
    *,
    cell_size_m: int = CELL_SIZE_M,
    minimum_fraction: float = 0.05,
) -> gpd.GeoDataFrame:
    """Create stable clipped square cells over a configured study polygon."""
    if area.geometry is None:
        raise ValueError("the urban atlas requires a polygon study area")
    study_geometry = gpd.GeoSeries([area.geometry], crs="EPSG:4326").to_crs(METRIC_CRS).iloc[0]
    minx, miny, maxx, maxy = study_geometry.bounds
    x_start = math.floor(minx / cell_size_m) * cell_size_m
    y_start = math.floor(miny / cell_size_m) * cell_size_m
    x_stop = math.ceil(maxx / cell_size_m) * cell_size_m
    y_stop = math.ceil(maxy / cell_size_m) * cell_size_m
    minimum_area = cell_size_m * cell_size_m * minimum_fraction

    records: list[dict[str, Any]] = []
    x_values = np.arange(x_start, x_stop, cell_size_m)
    y_values = np.arange(y_start, y_stop, cell_size_m)
    for x_index, x0 in enumerate(x_values):
        for y_index, y0 in enumerate(y_values):
            geometry = box(x0, y0, x0 + cell_size_m, y0 + cell_size_m).intersection(
                study_geometry
            )
            if geometry.is_empty or geometry.area < minimum_area:
                continue
            records.append(
                {
                    "cell_id": f"C{x_index:03d}_{y_index:03d}",
                    "grid_x": x_index,
                    "grid_y": y_index,
                    "area_km2": geometry.area / 1_000_000,
                    "geometry": geometry,
                }
            )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=METRIC_CRS)


def land_use_group(value: Any) -> str:
    """Reduce Overture land-use classes to atlas-readable themes."""
    normalized = str(value or "").lower().replace("-", "_")
    rules = {
        "residential": ("residential", "housing", "apartments"),
        "commercial": ("commercial", "retail", "market", "business"),
        "industrial": ("industrial", "warehouse", "quarry", "construction"),
        "institutional": (
            "school",
            "college",
            "university",
            "hospital",
            "institutional",
            "government",
            "civic",
            "religious",
            "cemetery",
            "grave_yard",
        ),
        "green_recreation": (
            "park",
            "grass",
            "garden",
            "playground",
            "pitch",
            "recreation",
            "forest",
            "green",
            "golf",
            "farmland",
        ),
        "transport": ("transport", "railway", "airport", "parking", "highway"),
    }
    for group, keywords in rules.items():
        if any(keyword in normalized for keyword in keywords):
            return group
    return "other"


def service_group(category: str) -> str | None:
    """Assign a detailed Overture category to a service-distance theme."""
    normalized = category.lower().replace("-", "_")
    patterns = {
        "healthcare": ("hospital", "clinic", "medical", "doctor", "health_centre"),
        "education": ("school", "college", "university", "educational"),
        "market": ("market", "supermarket", "shopping", "mall", "grocery"),
        "park": ("park", "garden", "playground", "recreation_ground"),
        "transport": ("bus", "rail", "transit", "metro", "subway", "airport", "taxi"),
    }
    for group, keywords in patterns.items():
        if any(keyword in normalized for keyword in keywords):
            return group
    return None


def _point_frame(gdf: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    frame = gdf[columns + [gdf.geometry.name]].copy()
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]
    frame.geometry = frame.geometry.representative_point()
    return frame


def _join_points_to_cells(
    points: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if points.empty:
        return points.assign(cell_id=pd.Series(dtype="object"))
    return gpd.sjoin(
        points,
        cells[["cell_id", "geometry"]],
        how="inner",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")


def _nearest_distances(
    origins: gpd.GeoSeries,
    destinations: gpd.GeoSeries,
) -> np.ndarray:
    if destinations.empty:
        return np.full(len(origins), np.nan)
    origin_xy = np.column_stack((origins.x.to_numpy(), origins.y.to_numpy()))
    destination_xy = np.column_stack(
        (destinations.x.to_numpy(), destinations.y.to_numpy())
    )
    distances, _ = cKDTree(destination_xy).query(origin_xy, k=1)
    return distances


def _add_building_features(
    cells: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
) -> None:
    metric = buildings.to_crs(cells.crs)
    metric = metric.loc[metric.geometry.notna() & ~metric.geometry.is_empty].copy()
    metric["footprint_m2"] = metric.geometry.area
    points = _point_frame(metric, ["footprint_m2"])
    joined = _join_points_to_cells(points, cells)
    grouped = joined.groupby("cell_id").agg(
        building_count=("footprint_m2", "size"),
        building_footprint_m2=("footprint_m2", "sum"),
        median_building_footprint_m2=("footprint_m2", "median"),
    )
    for column in grouped:
        cells[column] = cells["cell_id"].map(grouped[column]).fillna(0)
    cells["building_footprint_share"] = (
        cells["building_footprint_m2"] / (cells["area_km2"] * 1_000_000)
    ).clip(upper=1.0)
    cells["building_density_km2"] = cells["building_count"] / cells["area_km2"]


def _add_poi_features(cells: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> None:
    metric = places.to_crs(cells.crs).copy()
    metric["primary_category"] = (
        metric["categories"].map(poi_primary_category)
        if "categories" in metric
        else "uncategorized"
    )
    metric["poi_group"] = metric["primary_category"].map(poi_group)
    metric["service_group"] = metric["primary_category"].map(service_group)
    points = _point_frame(metric, ["primary_category", "poi_group", "service_group"])
    joined = _join_points_to_cells(points, cells)

    total_counts = joined.groupby("cell_id").size()
    cells["poi_count"] = cells["cell_id"].map(total_counts).fillna(0).astype(int)
    cells["poi_density_km2"] = cells["poi_count"] / cells["area_km2"]

    grouped = joined.groupby(["cell_id", "poi_group"]).size().unstack(fill_value=0)
    for group, base_column in POI_COLUMNS.items():
        values = grouped[group] if group in grouped else pd.Series(dtype=float)
        cells[base_column] = cells["cell_id"].map(values).fillna(0).astype(int)
        cells[f"{base_column}_density_km2"] = cells[base_column] / cells["area_km2"]

    origin_points = cells.geometry.representative_point()
    for group in ("healthcare", "education", "market", "park", "transport"):
        subset = points.loc[points["service_group"] == group]
        cells[f"distance_{group}_m"] = _nearest_distances(origin_points, subset.geometry)


def _add_land_use_features(cells: gpd.GeoDataFrame, land_use: gpd.GeoDataFrame) -> None:
    metric = land_use.to_crs(cells.crs).copy()
    metric = metric.loc[
        metric.geometry.notna()
        & ~metric.geometry.is_empty
        & metric.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ]
    metric["land_use_group"] = (
        metric["class"].map(land_use_group) if "class" in metric else "other"
    )
    if metric.empty:
        for column in LAND_USE_COLUMNS.values():
            cells[column] = 0.0
        cells["mapped_landuse_share"] = 0.0
        return

    intersections = gpd.overlay(
        cells[["cell_id", "geometry"]],
        metric[["land_use_group", "geometry"]],
        how="intersection",
        keep_geom_type=False,
    )
    intersections["mapped_area_m2"] = intersections.geometry.area
    grouped = (
        intersections.groupby(["cell_id", "land_use_group"])["mapped_area_m2"]
        .sum()
        .unstack(fill_value=0)
    )
    cell_area = cells.set_index("cell_id")["area_km2"] * 1_000_000
    for group, column in LAND_USE_COLUMNS.items():
        area = grouped[group] if group in grouped else pd.Series(dtype=float)
        cells[column] = (
            cells["cell_id"].map(area).fillna(0).to_numpy()
            / (cells["area_km2"] * 1_000_000)
        ).clip(upper=1.0)
    mapped_area = intersections.groupby("cell_id")["mapped_area_m2"].sum()
    cells["mapped_landuse_share"] = (
        cells["cell_id"].map(mapped_area).fillna(0).to_numpy()
        / (cells["area_km2"] * 1_000_000)
    ).clip(upper=1.0)
    del cell_area


def _add_road_features(
    cells: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
) -> None:
    metric_roads = roads.to_crs(cells.crs)
    pieces = gpd.overlay(
        metric_roads[["geometry"]],
        cells[["cell_id", "geometry"]],
        how="intersection",
        keep_geom_type=False,
    )
    pieces = pieces.loc[pieces.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    pieces["road_length_m"] = pieces.geometry.length
    lengths = pieces.groupby("cell_id")["road_length_m"].sum()
    cells["road_length_km"] = cells["cell_id"].map(lengths).fillna(0) / 1_000
    cells["road_density_km_km2"] = cells["road_length_km"] / cells["area_km2"]

    from_counts = road_edges["from_node_id"].astype(str)
    to_counts = road_edges["to_node_id"].astype(str)
    degrees = Counter(pd.concat([from_counts, to_counts]).tolist())
    nodes = road_nodes.to_crs(cells.crs).copy()
    nodes["node_id"] = nodes["node_id"].astype(str)
    nodes["road_degree"] = nodes["node_id"].map(degrees).fillna(0).astype(int)
    joined = _join_points_to_cells(nodes[["node_id", "road_degree", "geometry"]], cells)
    intersection_counts = joined.loc[joined["road_degree"] >= 3].groupby("cell_id").size()
    cells["intersection_count"] = (
        cells["cell_id"].map(intersection_counts).fillna(0).astype(int)
    )
    cells["intersection_density_km2"] = cells["intersection_count"] / cells["area_km2"]


def _add_contiguity_features(
    cells: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, nx.Graph]:
    indexed = cells.set_index("cell_id")
    _, edges = c2g.contiguity_graph(indexed, contiguity="queen")
    graph = nx.Graph()
    graph.add_nodes_from(indexed.index)
    graph.add_edges_from((str(source), str(target)) for source, target in edges.index)
    degree = nx.degree_centrality(graph)
    betweenness = nx.betweenness_centrality(graph, normalized=True)
    cells["cell_neighbor_count"] = cells["cell_id"].map(dict(graph.degree())).fillna(0)
    cells["cell_degree_centrality"] = cells["cell_id"].map(degree).fillna(0)
    cells["cell_betweenness_centrality"] = cells["cell_id"].map(betweenness).fillna(0)
    return edges, graph


def _cluster_descriptor(
    cluster_rows: pd.DataFrame,
    all_rows: pd.DataFrame,
) -> str:
    standard = (cluster_rows.mean() - all_rows.mean()) / all_rows.std(ddof=0).replace(0, 1)
    phrases = {
        "building_footprint_share": ("high building coverage", "low building coverage"),
        "building_density_km2": ("building-dense", "building-sparse"),
        "road_density_km_km2": ("road-dense", "road-sparse"),
        "intersection_density_km2": ("intersection-rich", "intersection-sparse"),
        "poi_density_km2": ("high-activity", "service-light"),
        "poi_healthcare_density_km2": ("healthcare-rich", "limited healthcare"),
        "poi_education_density_km2": ("education-rich", "limited education"),
        "poi_food_drink_density_km2": ("food/activity-rich", "limited food activity"),
        "poi_retail_markets_density_km2": ("retail-rich", "limited retail"),
        "poi_transport_density_km2": ("transport-POI-rich", "limited transport POIs"),
        "poi_civic_religious_density_km2": ("civic/religious-rich", "limited civic POIs"),
        "poi_recreation_culture_density_km2": (
            "recreation/culture-rich",
            "limited recreation POIs",
        ),
        "landuse_residential_share": ("residential land use", "limited residential mapping"),
        "landuse_commercial_share": ("commercial land use", "limited commercial mapping"),
        "landuse_industrial_share": ("industrial land use", "limited industrial mapping"),
        "landuse_institutional_share": (
            "institutional land use",
            "limited institutional mapping",
        ),
        "landuse_green_share": ("green/recreation land use", "limited green mapping"),
        "distance_healthcare_m": ("healthcare-distant", "healthcare-near"),
        "distance_education_m": ("education-distant", "education-near"),
        "distance_market_m": ("market-distant", "market-near"),
        "distance_park_m": ("park-distant", "park-near"),
        "distance_transport_m": ("transport-distant", "transport-near"),
    }
    candidates = standard[[column for column in phrases if column in standard]]
    strongest = candidates.abs().sort_values(ascending=False).head(2).index
    descriptions = [
        phrases[column][0 if standard[column] >= 0 else 1] for column in strongest
    ]
    return " / ".join(descriptions)


def classify_urban_functions(
    cells: gpd.GeoDataFrame,
    *,
    cluster_count: int = CLUSTER_COUNT,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Fit a reproducible PCA/K-Means baseline and attach cell classes."""
    candidate_columns = [column for column in ATLAS_FEATURE_COLUMNS if column in cells]
    candidates = cells[candidate_columns].replace([np.inf, -np.inf], np.nan).copy()
    nonzero_fraction = candidates.fillna(0).ne(0).mean()
    feature_columns = [
        column
        for column in candidate_columns
        if nonzero_fraction[column] >= 0.02 and candidates[column].nunique(dropna=True) > 1
    ]
    excluded_features = sorted(set(candidate_columns) - set(feature_columns))
    values = candidates[feature_columns]
    values = values.fillna(values.median(numeric_only=True)).fillna(0)
    distance_columns = [column for column in feature_columns if column.startswith("distance_")]
    density_columns = [column for column in feature_columns if "density" in column]
    values[density_columns + distance_columns] = np.log1p(
        values[density_columns + distance_columns].clip(lower=0)
    )

    scaled = np.clip(StandardScaler().fit_transform(values), -5.0, 5.0)
    clusters = min(cluster_count, max(2, len(cells) // 20))
    model = KMeans(n_clusters=clusters, random_state=random_seed, n_init=20)
    labels = model.fit_predict(scaled)
    pca = PCA(n_components=2, random_state=random_seed)
    coordinates = pca.fit_transform(scaled)

    cells["cluster_id"] = labels + 1
    cells["pca_1"] = coordinates[:, 0]
    cells["pca_2"] = coordinates[:, 1]
    descriptors = {
        cluster + 1: _cluster_descriptor(values.loc[labels == cluster], values)
        for cluster in range(clusters)
    }
    cells["urban_class"] = cells["cluster_id"].map(
        {
            cluster: f"Cluster {cluster} · {descriptor}"
            for cluster, descriptor in descriptors.items()
        }
    )
    return {
        "method": "StandardScaler + PCA (visualization) + K-Means",
        "cluster_count": clusters,
        "random_seed": random_seed,
        "feature_columns": feature_columns,
        "excluded_sparse_or_constant_features": excluded_features,
        "pca_explained_variance": [
            round(float(value), 4) for value in pca.explained_variance_ratio_
        ],
        "cluster_descriptors": {str(key): value for key, value in descriptors.items()},
    }


def build_urban_atlas(
    layers: Mapping[str, gpd.GeoDataFrame],
    roads: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
    area: StudyArea,
    *,
    cell_size_m: int = CELL_SIZE_M,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, Any]]:
    """Build cell features, contiguity relations, and baseline urban classes."""
    cells = make_analysis_grid(area, cell_size_m=cell_size_m)
    _add_building_features(cells, layers["building"])
    _add_poi_features(cells, layers["place"])
    _add_land_use_features(cells, layers["land_use"])
    _add_road_features(cells, roads, road_nodes, road_edges)
    contiguity_edges, graph = _add_contiguity_features(cells)
    classification = classify_urban_functions(cells, random_seed=area.random_seed)

    class_counts = cells["urban_class"].value_counts().sort_index()
    summary = {
        "study_area": area.name,
        "study_area_slug": area.slug,
        "cell_size_m": cell_size_m,
        "cell_count": len(cells),
        "represented_area_km2": round(float(cells["area_km2"].sum()), 3),
        "contiguity_method": "City2Graph queen contiguity",
        "contiguity_edges": graph.number_of_edges(),
        "connected_components": nx.number_connected_components(graph),
        "classification": classification,
        "urban_class_counts": [
            {"urban_class": label, "cells": int(count)}
            for label, count in class_counts.items()
        ],
        "interpretation": (
            "Exploratory cell classes derived from mapped Overture and road-network features. "
            "They are not administrative neighborhoods or ground-truth land-use labels."
        ),
        "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
    }
    return cells, contiguity_edges, summary
