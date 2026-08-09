# DhakaGraph roadmap

## Milestone 1: expanded Dhaka road pilot

Build, cache, inspect, and map the drive network from Airport and Uttara to
Sayedabad while covering Mirpur, Gulshan, Badda, and Bashundhara. Keep the
original Shahbag radius as a smaller test area. Use structural graph metrics only
and label them clearly as non-traffic results.

## Milestone 2: OSM versus Overture audit

Compare road, building, place, water, and land-use coverage over the same pilot
boundary. Record feature counts, missing attributes, geometry validity, and
download date before selecting a source per layer.

Status: the Overture baseline was implemented on 2026-08-04 with release
`2026-07-22.0`. Six feature themes, a connector-split road graph, a layer audit,
ranked place and land-use categories, a static overview, and an interactive map
are published. A direct spatial mismatch analysis between the OSM and Overture
road geometries remains a future comparison task.

## Milestone 3: places and accessibility

Attach hospitals, universities, schools, markets, parks, and stations to the
road graph. Produce distance-based accessibility summaries and isochrones.

Status: Stages 1 and 2 are complete. The urban-function foundation aggregates
mapped places, land use, buildings, roads, intersections, service distances and
contiguity centrality into 643 reproducible 750 m cells. Network walking times,
10/15/30-minute service counts, modeled driving comparisons and transparent
demand-adjusted service-gap scores are now published. Transit remains unmodeled
until a validated Dhaka GTFS source is available. Stage 3 now adds an anchor-based
neighborhood-similarity explorer over the urban and accessibility features. The
next stages add flood-resilience simulation and population-weighted service
equity. The equity baseline currently uses a mapped built/residential-intensity
proxy and accepts an external cell population table.

## Milestone 4: public transport

Audit available Dhaka bus and MRT data. Only use City2Graph's GTFS travel graph
when stop order, service calendars, and headways are sufficiently documented.

## Milestone 5: flood scenarios

Overlay documented flood depth or duration data, define transparent edge-cost
rules, and compare normal and disrupted accessibility. Keep scenario outputs
separate from claims about observed events.

Status: a first network-sensitivity simulation is published using transparent
distance-to-water elevation proxies. It currently ranks inundated road edges and
anchor connectivity; historical flood-depth layers and cell-level service-loss
analysis remain the next improvement.

## Milestone 6: optional graph learning

Introduce PyTorch Geometric only after a useful target, labels, baseline, and
evaluation split have been defined.

