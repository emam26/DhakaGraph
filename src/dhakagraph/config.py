"""Configuration objects for reproducible study areas."""

from dataclasses import dataclass

from shapely.geometry import Point, Polygon

PolygonCoordinates = tuple[tuple[float, float], ...]
AnchorCoordinates = tuple[tuple[str, float, float], ...]


@dataclass(frozen=True, slots=True)
class StudyArea:
    """A reproducible point-radius or polygon OpenStreetMap study area."""

    slug: str
    name: str
    center_lat: float
    center_lon: float
    radius_m: int | None = None
    polygon_lon_lat: PolygonCoordinates = ()
    anchors_lon_lat: AnchorCoordinates = ()
    network_type: str = "drive"
    centrality_samples: int = 300
    top_n: int = 30
    random_seed: int = 42

    def __post_init__(self) -> None:
        """Reject configurations that would produce ambiguous analyses."""
        if not self.slug or any(char.isspace() for char in self.slug):
            raise ValueError("slug must be non-empty and contain no whitespace")
        if not -90 <= self.center_lat <= 90:
            raise ValueError("center_lat must be between -90 and 90")
        if not -180 <= self.center_lon <= 180:
            raise ValueError("center_lon must be between -180 and 180")
        if self.radius_m is None and not self.polygon_lon_lat:
            raise ValueError("either radius_m or polygon_lon_lat must be provided")
        if self.radius_m is not None and self.polygon_lon_lat:
            raise ValueError("radius_m and polygon_lon_lat are mutually exclusive")
        if self.radius_m is not None and self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.polygon_lon_lat:
            if len(self.polygon_lon_lat) < 3:
                raise ValueError("polygon_lon_lat must contain at least three coordinates")
            geometry = Polygon(self.polygon_lon_lat)
            if not geometry.is_valid or geometry.is_empty:
                raise ValueError("polygon_lon_lat must form a valid polygon")
            if not geometry.covers(Point(self.center_lon, self.center_lat)):
                raise ValueError("the configured center must lie within the study polygon")
        for label, longitude, latitude in self.anchors_lon_lat:
            if not label:
                raise ValueError("study-area anchor labels must be non-empty")
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                raise ValueError("study-area anchor coordinates are invalid")
            if self.geometry is not None and not self.geometry.covers(Point(longitude, latitude)):
                raise ValueError(f"study-area anchor {label!r} lies outside the polygon")
        if self.centrality_samples <= 0:
            raise ValueError("centrality_samples must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")

    @property
    def center(self) -> tuple[float, float]:
        """Return the `(latitude, longitude)` tuple expected by OSMnx."""
        return self.center_lat, self.center_lon

    @property
    def geometry(self) -> Polygon | None:
        """Return the polygon geometry, or ``None`` for a radius-based area."""
        return Polygon(self.polygon_lon_lat) if self.polygon_lon_lat else None

    @property
    def selection_method(self) -> str:
        """Describe how OSMnx should select the network."""
        return "polygon" if self.polygon_lon_lat else "point_radius"


CENTRAL_DHAKA_PILOT = StudyArea(
    slug="central_dhaka_shahbag",
    name="Central Dhaka pilot centered near Shahbag",
    center_lat=23.7386,
    center_lon=90.3954,
    radius_m=2_500,
)


EXPANDED_DHAKA_STUDY = StudyArea(
    slug="airport_uttara_mirpur_gulshan_badda_bashundhara_sayedabad",
    name="Expanded Dhaka: Uttara-Airport to Sayedabad, Mirpur to Bashundhara",
    center_lat=23.798,
    center_lon=90.398,
    polygon_lon_lat=(
        (90.312, 23.765),
        (90.312, 23.840),
        (90.338, 23.900),
        (90.470, 23.900),
        (90.486, 23.815),
        (90.478, 23.755),
        (90.455, 23.695),
        (90.398, 23.695),
        (90.352, 23.730),
    ),
    anchors_lon_lat=(
        ("Airport", 90.4053032, 23.8431441),
        ("Uttara", 90.3926893, 23.8693275),
        ("Mirpur", 90.3640891, 23.8123629),
        ("Gulshan", 90.4138705, 23.7948921),
        ("Badda", 90.4463012, 23.7765425),
        ("Bashundhara", 90.4368229, 23.8189265),
        ("Sayedabad", 90.4275444, 23.7153498),
    ),
    centrality_samples=300,
    top_n=50,
)

# Backward-compatible name retained for notebooks built against the first expanded pilot.
AIRPORT_UTTARA_MIRPUR_SAYEDABAD = EXPANDED_DHAKA_STUDY


STUDY_AREAS = {
    "expanded": EXPANDED_DHAKA_STUDY,
    "shahbag": CENTRAL_DHAKA_PILOT,
}
