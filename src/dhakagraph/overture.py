"""Overture Maps acquisition, processing, and descriptive audit helpers."""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import city2graph as c2g
import geopandas as gpd
from shapely.geometry import Point

from dhakagraph.config import StudyArea

OVERTURE_RELEASE = "2026-07-22.0"
OVERTURE_TYPES = ("building", "segment", "connector", "place", "land_use", "water")
METRIC_CRS = "EPSG:32646"


def _study_geometry(area: StudyArea):
    """Return a WGS84 polygon for polygon- or radius-based study areas."""
    if area.geometry is not None:
        return area.geometry
    center = gpd.GeoSeries(
        [Point(area.center_lon, area.center_lat)],
        crs="EPSG:4326",
    ).to_crs(METRIC_CRS)
    return center.buffer(area.radius_m).to_crs("EPSG:4326").iloc[0]


def ensure_overture_cli() -> Path:
    """Make the virtual-environment Overture CLI discoverable by City2Graph."""
    executable = shutil.which("overturemaps")
    if executable:
        return Path(executable)

    scripts_dir = Path(sys.executable).resolve().parent
    candidate = scripts_dir / ("overturemaps.exe" if os.name == "nt" else "overturemaps")
    if not candidate.exists():
        raise RuntimeError(
            "The overturemaps CLI is unavailable. Install the project environment with "
            "`python -m pip install -e .` before running the Overture pipeline."
        )
    os.environ["PATH"] = f"{scripts_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return candidate


def load_or_download_overture(
    area: StudyArea,
    raw_dir: Path,
    *,
    release: str = OVERTURE_RELEASE,
    types: Iterable[str] = OVERTURE_TYPES,
    refresh: bool = False,
) -> tuple[dict[str, gpd.GeoDataFrame], dict[str, Path]]:
    """Load cached Overture layers or download each requested layer through City2Graph."""
    selected_types = tuple(dict.fromkeys(types))
    invalid = sorted(set(selected_types) - set(OVERTURE_TYPES))
    if invalid:
        raise ValueError(f"unsupported Overture layer(s): {', '.join(invalid)}")

    cache_dir = raw_dir / "overture" / area.slug / release
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = {layer_type: cache_dir / f"{layer_type}.geojson" for layer_type in selected_types}
    layers: dict[str, gpd.GeoDataFrame] = {}

    for layer_type in selected_types:
        path = paths[layer_type]
        if path.exists() and not refresh:
            layers[layer_type] = gpd.read_file(path, encoding="utf-8")
            continue

        ensure_overture_cli()
        downloaded = c2g.load_overture_data(
            area=_study_geometry(area),
            types=[layer_type],
            output_dir=str(cache_dir),
            save_to_file=True,
            return_data=True,
            release=release,
            connect_timeout=10,
            request_timeout=60,
            keep_outer_neighbors=layer_type == "segment",
        )
        layers[layer_type] = downloaded[layer_type]

    return layers, paths


def process_overture_roads(
    layers: Mapping[str, gpd.GeoDataFrame],
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Split Overture roads at connectors and convert them to graph GeoDataFrames."""
    segments = layers["segment"].to_crs(METRIC_CRS)
    connectors = layers["connector"].to_crs(METRIC_CRS)
    roads = segments.loc[segments.get("subtype", "") == "road"].copy()
    if roads.empty:
        raise ValueError("Overture returned no road segments for the configured study area")

    processed = c2g.process_overture_segments(
        roads,
        connectors_gdf=connectors,
        get_barriers=True,
        threshold=1.0,
    )
    nodes, edges = c2g.segments_to_graph(processed, directed=False, multigraph=True)
    return processed, nodes, edges


def export_overture_graph_layers(
    processed: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    edges: gpd.GeoDataFrame,
    processed_dir: Path,
    slug: str,
) -> dict[str, Path]:
    """Save the graph-ready Overture road products for GIS inspection."""
    output_dir = processed_dir / "overture"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "processed_roads": output_dir / f"{slug}_processed_roads.geojson",
        "road_nodes": output_dir / f"{slug}_road_nodes.geojson",
        "road_edges": output_dir / f"{slug}_road_edges.geojson",
    }
    processed.to_crs("EPSG:4326").to_file(outputs["processed_roads"], driver="GeoJSON")
    nodes.to_crs("EPSG:4326").reset_index().to_file(outputs["road_nodes"], driver="GeoJSON")
    edges.to_crs("EPSG:4326").reset_index().to_file(outputs["road_edges"], driver="GeoJSON")
    return outputs


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def poi_primary_category(value: Any) -> str:
    """Extract an Overture place's primary category from native or serialized metadata."""
    category = _mapping(value).get("primary")
    return str(category).strip() if category else "uncategorized"


def poi_primary_name(value: Any) -> str:
    """Extract a readable Overture place name from native or serialized metadata."""
    name = _mapping(value).get("primary")
    return str(name).strip() if name else "Unnamed place"


def poi_group(category: str) -> str:
    """Reduce Overture's detailed place taxonomy to map-readable study categories."""
    normalized = category.lower().replace("-", "_")
    rules = {
        "Healthcare": ("hospital", "clinic", "doctor", "medical", "pharmacy", "dentist"),
        "Education": ("school", "university", "college", "education", "training", "library"),
        "Food & drink": ("restaurant", "cafe", "coffee", "food", "bakery", "bar", "tea"),
        "Retail & markets": ("shop", "store", "retail", "market", "mall", "supermarket"),
        "Transport": ("bus", "rail", "transit", "airport", "parking", "taxi", "transport"),
        "Civic & religious": (
            "government",
            "public",
            "police",
            "fire_station",
            "post_office",
            "mosque",
            "church",
            "temple",
            "relig",
        ),
        "Recreation & culture": (
            "park",
            "sport",
            "fitness",
            "entertainment",
            "museum",
            "culture",
            "cinema",
        ),
    }
    for group, keywords in rules.items():
        if any(keyword in normalized for keyword in keywords):
            return group
    return "Other"


def _counts(records: Iterable[str], *, limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"category": category, "count": count}
        for category, count in Counter(records).most_common(limit)
    ]


def layer_audit(layers: Mapping[str, gpd.GeoDataFrame]) -> list[dict[str, Any]]:
    """Return compact completeness and geometry diagnostics for every Overture layer."""
    rows = []
    for layer_type in OVERTURE_TYPES:
        gdf = layers.get(layer_type, gpd.GeoDataFrame(geometry=[]))
        geometry_types = ", ".join(sorted(gdf.geometry.geom_type.dropna().unique()))
        rows.append(
            {
                "layer": layer_type,
                "features": len(gdf),
                "valid_geometries": int(gdf.geometry.is_valid.sum()) if len(gdf) else 0,
                "empty_geometries": int(gdf.geometry.is_empty.sum()) if len(gdf) else 0,
                "geometry_types": geometry_types,
                "attribute_columns": max(len(gdf.columns) - 1, 0),
            }
        )
    return rows


def overture_summary(
    layers: Mapping[str, gpd.GeoDataFrame],
    processed_roads: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
    area: StudyArea,
    release: str,
) -> dict[str, Any]:
    """Summarize Overture coverage without presenting it as observed traffic or activity."""
    projected = {
        name: gdf.to_crs(METRIC_CRS) if not gdf.empty else gdf.copy()
        for name, gdf in layers.items()
    }
    study_area_km2 = gpd.GeoSeries([_study_geometry(area)], crs="EPSG:4326").to_crs(
        METRIC_CRS
    ).area.iloc[0] / 1_000_000
    buildings = projected.get("building", gpd.GeoDataFrame(geometry=[]))
    roads = projected.get("segment", gpd.GeoDataFrame(geometry=[]))
    if "subtype" in roads:
        roads = roads.loc[roads["subtype"] == "road"]
    places = layers.get("place", gpd.GeoDataFrame(geometry=[]))
    land_use = layers.get("land_use", gpd.GeoDataFrame(geometry=[]))

    poi_categories = (
        [poi_primary_category(value) for value in places["categories"]]
        if "categories" in places
        else []
    )
    poi_groups = [poi_group(category) for category in poi_categories]
    land_use_classes = (
        [str(value) if value else "unclassified" for value in land_use["class"]]
        if "class" in land_use
        else []
    )
    feature_counts = {row["layer"]: row["features"] for row in layer_audit(layers)}

    return {
        "study_area": area.name,
        "study_area_slug": area.slug,
        "selection_method": area.selection_method,
        "study_area_km2": round(float(study_area_km2), 3),
        "overture_release": release,
        "feature_counts": feature_counts,
        "building_footprint_km2": round(
            float(buildings.geometry.area.sum() / 1_000_000) if len(buildings) else 0.0,
            3,
        ),
        "building_footprint_share": round(
            float(buildings.geometry.area.sum() / 1_000_000 / study_area_km2)
            if len(buildings)
            else 0.0,
            4,
        ),
        "overture_road_length_km": round(
            float(roads.geometry.length.sum() / 1_000) if len(roads) else 0.0,
            3,
        ),
        "processed_road_segments": len(processed_roads),
        "road_graph_nodes": len(road_nodes),
        "road_graph_edges": len(road_edges),
        "top_poi_categories": _counts(poi_categories),
        "poi_groups": _counts(poi_groups),
        "top_land_use_classes": _counts(land_use_classes),
        "interpretation": (
            "Coverage and topology from Overture Maps; counts are mapped features, not "
            "observed visits, traffic, or population."
        ),
        "data_attribution": "© OpenStreetMap contributors, Overture Maps Foundation",
    }
