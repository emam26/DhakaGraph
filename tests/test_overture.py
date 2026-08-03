import geopandas as gpd
from shapely.geometry import LineString, Point, box

from dhakagraph.config import StudyArea
from dhakagraph.overture import (
    layer_audit,
    load_or_download_overture,
    poi_group,
    poi_primary_category,
    poi_primary_name,
)
from dhakagraph.overture_maps import building_density_grid


def test_overture_category_and_name_parsing() -> None:
    assert poi_primary_category({"primary": "general_hospital"}) == "general_hospital"
    assert poi_primary_category('{"primary": "university"}') == "university"
    assert poi_primary_name("{'primary': 'Dhaka Medical College'}") == "Dhaka Medical College"
    assert poi_group("general_hospital") == "Healthcare"
    assert poi_group("bus_station") == "Transport"


def test_building_density_grid_counts_occupied_cells() -> None:
    buildings = gpd.GeoDataFrame(
        geometry=[
            box(90.4, 23.7, 90.4001, 23.7001),
            box(90.4002, 23.7002, 90.4003, 23.7003),
            box(90.42, 23.72, 90.4201, 23.7201),
        ],
        crs="EPSG:4326",
    )
    grid = building_density_grid(buildings, cell_size_m=750)
    assert grid["building_count"].sum() == 3
    assert len(grid) == 2
    assert (grid["footprint_m2"] > 0).all()


def test_cached_overture_layers_do_not_redownload(tmp_path, monkeypatch) -> None:
    area = StudyArea("sample", "Sample", 23.7, 90.4, radius_m=1_000)
    cache_dir = tmp_path / "overture" / area.slug / "test-release"
    cache_dir.mkdir(parents=True)
    sample = gpd.GeoDataFrame(geometry=[Point(90.4, 23.7)], crs="EPSG:4326")
    sample.to_file(cache_dir / "place.geojson", driver="GeoJSON")

    def fail_download(*_args, **_kwargs):
        raise AssertionError("cache should be used")

    monkeypatch.setattr("dhakagraph.overture.c2g.load_overture_data", fail_download)
    layers, paths = load_or_download_overture(
        area,
        tmp_path,
        release="test-release",
        types=["place"],
    )
    assert len(layers["place"]) == 1
    assert paths["place"].exists()


def test_layer_audit_reports_geometry_quality() -> None:
    layers = {
        "segment": gpd.GeoDataFrame(
            geometry=[LineString([(90.4, 23.7), (90.41, 23.71)])],
            crs="EPSG:4326",
        )
    }
    rows = {row["layer"]: row for row in layer_audit(layers)}
    assert rows["segment"]["features"] == 1
    assert rows["segment"]["valid_geometries"] == 1
    assert rows["building"]["features"] == 0
