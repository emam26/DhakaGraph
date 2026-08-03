# Data-source rules

## OpenStreetMap

Use OSMnx for the initial road network and points of interest. Cache every query,
record the extraction date, and retain the required attribution:
`© OpenStreetMap contributors, ODbL`.

## Overture Maps

Use City2Graph's `load_overture_data` for the comparison stage. Pin or record the
Overture release and preserve each feature's source metadata. Overture features
may themselves include OpenStreetMap-derived content.

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

