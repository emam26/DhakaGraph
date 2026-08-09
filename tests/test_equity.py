"""Tests for population-weighted service equity."""

import geopandas as gpd
from shapely.geometry import box

from dhakagraph.equity import build_population_weighted_equity


def test_equity_uses_explicit_population_weights() -> None:
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["a", "b"],
            "building_density_km2": [10, 20],
            "landuse_residential_share": [0.8, 0.2],
            "building_footprint_share": [0.4, 0.5],
            "walk_minutes_healthcare": [20, 5],
            "walk_healthcare_15min_count": [0, 4],
        },
        geometry=[box(90, 23, 90.01, 23.01), box(90.01, 23, 90.02, 23.01)],
        crs="EPSG:4326",
    )
    result, rankings, summary = build_population_weighted_equity(cells)
    assert summary["population_source"].startswith("Mapped")
    assert len(rankings) == 2
    assert round(float(result["population_weight"].sum()), 6) == 1.0
    score_a = result.loc[result["cell_id"] == "a", "equity_gap_healthcare"].iloc[0]
    score_b = result.loc[result["cell_id"] == "b", "equity_gap_healthcare"].iloc[0]
    assert score_a > score_b
