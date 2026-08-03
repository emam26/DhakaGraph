# DhakaGraph roadmap

## Milestone 1: central-Dhaka road pilot

Build, cache, inspect, and map a small drive network centered near Shahbag.
Use structural graph metrics only and label them clearly as non-traffic results.

## Milestone 2: OSM versus Overture audit

Compare road, building, place, water, and land-use coverage over the same pilot
boundary. Record feature counts, missing attributes, geometry validity, and
download date before selecting a source per layer.

## Milestone 3: places and accessibility

Attach hospitals, universities, schools, markets, parks, and stations to the
road graph. Produce distance-based accessibility summaries and isochrones.

## Milestone 4: public transport

Audit available Dhaka bus and MRT data. Only use City2Graph's GTFS travel graph
when stop order, service calendars, and headways are sufficiently documented.

## Milestone 5: flood scenarios

Overlay documented flood depth or duration data, define transparent edge-cost
rules, and compare normal and disrupted accessibility. Keep scenario outputs
separate from claims about observed events.

## Milestone 6: optional graph learning

Introduce PyTorch Geometric only after a useful target, labels, baseline, and
evaluation split have been defined.

