# Data-source rules

## OpenStreetMap

Use OSMnx for the initial road network and points of interest. Cache every query,
record the extraction date, and retain the required attribution:
`© OpenStreetMap contributors, ODbL`.

## Overture Maps

The published audit uses City2Graph's `load_overture_data` with Overture release
`2026-07-22.0`, accessed on 2026-08-04. It queries `building`, `segment`,
`connector`, `place`, `land_use`, and `water` over the same fixed polygon as the
OSM study. Raw feature files are cached locally and ignored by Git; the release,
feature counts, geometry validity, and mapped coverage are recorded in the
published summary and audit table.

The road workflow filters transport segments to subtype `road`, projects them to
EPSG:32646, and uses connectors to split long Overture segments before graph
construction. Overture features may include OpenStreetMap-derived content, so the
two sources are not statistically independent. Preserve both Overture Maps
Foundation and upstream source attribution where applicable.

Feature counts describe the state of the map release. They do not measure people,
visits, population, traffic, or completeness on the ground.

## Transit

Treat historical Dhaka routes and research GTFS feeds as exploratory inputs.
Do not describe scheduled or assumed headways as observed service performance.

## Traffic

Road length, topology, and modeled travel costs are not live congestion. Any
future traffic layer must identify its collection period, spatial coverage,
license, and measurement method.

## Flooding

Keep forecast scenarios, historical flood extents, and real-time observations
as separate layers with separate interpretations.

