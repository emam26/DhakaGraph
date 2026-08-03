"""Configuration objects for reproducible study areas."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StudyArea:
    """A point-centered OpenStreetMap study area."""

    slug: str
    name: str
    center_lat: float
    center_lon: float
    radius_m: int
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
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.centrality_samples <= 0:
            raise ValueError("centrality_samples must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")

    @property
    def center(self) -> tuple[float, float]:
        """Return the `(latitude, longitude)` tuple expected by OSMnx."""
        return self.center_lat, self.center_lon


CENTRAL_DHAKA_PILOT = StudyArea(
    slug="central_dhaka_shahbag",
    name="Central Dhaka pilot centered near Shahbag",
    center_lat=23.7386,
    center_lon=90.3954,
    radius_m=2_500,
)
