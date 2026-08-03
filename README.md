# DhakaGraph

[![DhakaGraph interactive network explorer preview](outputs/maps/network_explorer_desktop.png)](https://emam26.github.io/DhakaGraph/outputs/maps/network_explorer.html)

**[Open the live road-network explorer →](https://emam26.github.io/DhakaGraph/outputs/maps/network_explorer.html)** ·
**[Explore the Overture urban layers →](https://emam26.github.io/DhakaGraph/outputs/maps/overture_explorer.html)** ·
**[Open the Urban Function Atlas →](https://emam26.github.io/DhakaGraph/outputs/maps/urban_atlas.html)**

DhakaGraph is a learning-oriented exploration of Dhaka as a spatial graph. The
project begins with roads and intersections, then adds places, public transport,
and flood scenarios as the underlying data are audited.

The default study covers a fixed polygon from Uttara and the Airport south to
Sayedabad, including Mirpur to the west and Gulshan, Badda, and Bashundhara to
the east. It combines an OpenStreetMap drive graph with an Overture Maps audit of
roads, buildings, places, land use, and water. City2Graph converts both road
sources into graph-ready structures. The results describe mapped coverage and
connectivity; they are not measurements of live Dhaka traffic or footfall.

## Current milestone

- Download and cache the expanded north-south Dhaka road graph.
- Convert the OSMnx graph through City2Graph.
- Measure graph size, connectivity, and approximate node betweenness.
- Export ranked intersections, a summary, processed spatial layers, and an HTML map.
- Load six Overture feature themes over the same fixed polygon and audit coverage.
- Split Overture road segments at connectors and export a second graph-ready network.
- Publish a layer-controlled Overture explorer and a four-panel visual summary.
- Describe Dhaka through a connected graph of 750 m analytical cells.
- Publish a transparent PCA/K-Means urban-function baseline with switchable metrics.
- Keep all network-dependent work outside the unit tests.

## Setup on Windows

City2Graph 1.0 requires Python 3.12 through 3.14. This machine has Python 3.14
available, so use a separate environment rather than the Python 3.11 GIFT
environment.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the pilot

```powershell
dhakagraph-pilot
```

Useful options:

```powershell
dhakagraph-pilot --centrality-samples 200 --top-n 40
dhakagraph-pilot --refresh
dhakagraph-pilot --area shahbag --radius 1500
```

The default `expanded` area uses a checked-in polygon containing Airport, Uttara,
Mirpur, Gulshan, Badda, Bashundhara, and Sayedabad anchors. The original 2.5 km
Shahbag pilot remains available with `--area shahbag`. The first run needs internet
access to query OpenStreetMap; later runs reuse the cached GraphML file unless
`--refresh` is supplied. See [docs/STUDY_AREA.md](docs/STUDY_AREA.md) for the
boundary definition.

## Run the Overture audit

```powershell
dhakagraph-overture
```

The Overture workflow follows the City2Graph pattern: query the same study
polygon, project the data to Dhaka's local UTM zone, keep road segments, split
them at connector features, and construct graph nodes and edges. The release is
pinned to `2026-07-22.0`; use `--refresh` only when you intentionally want to
download that release again. The cached raw GeoJSON is large and remains ignored
by Git.

[![Dhaka Overture Maps layer preview](outputs/maps/overture_preview.png)](https://emam26.github.io/DhakaGraph/outputs/maps/overture_explorer.html)

The current snapshot contains 566,618 mapped building footprints, 109,582 place
features, 51,663 transport segments, 2,423 land-use features, and 3,194 water
features. Processing the road segments at Overture connectors produces 43,330
graph nodes and 57,108 edges. Counts refer to mapped features, not people, visits,
or traffic volume.

## Run the urban studies

```powershell
dhakagraph-urban
```

Stage 1 divides the study polygon into 643 clipped 750 m cells and connects them
with City2Graph queen contiguity. Each cell receives building, POI, land-use,
road, intersection, service-distance and cell-centrality features. A reproducible
seven-cluster PCA/K-Means baseline then describes recurring combinations of those
mapped characteristics.

[![Dhaka Urban Function Atlas preview](outputs/maps/urban_atlas_preview.png)](https://emam26.github.io/DhakaGraph/outputs/maps/urban_atlas.html)

These clusters are exploratory descriptions, not administrative neighborhoods,
official land-use classes or evidence of observed human activity. Sparse or
constant variables are recorded and excluded from clustering rather than allowed
to create misleading one-cell classes.

## Outputs

The latest expanded Dhaka pilot snapshot is available online:

- [Explore the dynamic network dashboard](https://emam26.github.io/DhakaGraph/outputs/maps/network_explorer.html)
- [Explore Overture buildings, places, roads, land use, and water](https://emam26.github.io/DhakaGraph/outputs/maps/overture_explorer.html)
- [Explore the 750 m Dhaka Urban Function Atlas](https://emam26.github.io/DhakaGraph/outputs/maps/urban_atlas.html)
- [Open the interactive centrality map](https://emam26.github.io/DhakaGraph/outputs/maps/centrality_map.html)
- [View the full-size static map](outputs/maps/centrality_preview.png)
- [View the Overture four-panel preview](outputs/maps/overture_preview.png)
- [Read the network summary](outputs/tables/network_summary.json)
- [Read the Overture summary](outputs/tables/overture_summary.json)
- [Read the urban-atlas methodology and summary](outputs/tables/urban_atlas_summary.json)
- [Download the urban cell feature table](outputs/tables/urban_atlas_cells.csv)
- [Inspect the Overture layer audit](outputs/tables/overture_layer_audit.csv)
- [Browse Overture POI and land-use rankings](outputs/tables/overture_poi_categories.csv)
- [Read the extended network profile](outputs/tables/network_profile.json)
- [Browse the ranked intersections](outputs/tables/top_intersections.csv)

The dynamic explorer provides switchable betweenness/degree rankings, a visible-node
slider, street-name filtering, selectable intersections, topology sketches,
degree and road-class charts, named-road summaries, anchor focus controls, and an
illustrative Uttara-Airport-Mirpur-Sayedabad shortest-distance graph connection.
The Overture explorer adds switchable building-density, road, land-use, water,
place-category, and requested-anchor layers without drawing the study polygon as
a dashed border.

![Expanded Dhaka road-network centrality preview](outputs/maps/centrality_preview.png)

```text
data/raw/airport_uttara_mirpur_gulshan_badda_bashundhara_sayedabad_drive.graphml
data/processed/airport_uttara_mirpur_gulshan_badda_bashundhara_sayedabad_nodes.geojson
data/processed/airport_uttara_mirpur_gulshan_badda_bashundhara_sayedabad_edges.geojson
outputs/tables/network_summary.json
outputs/tables/network_profile.json
outputs/tables/top_intersections.csv
outputs/maps/centrality_map.html
outputs/maps/network_explorer.html
outputs/maps/network_explorer_desktop.png
outputs/maps/centrality_preview.png
outputs/maps/overture_explorer.html
outputs/maps/overture_preview.png
outputs/tables/overture_summary.json
outputs/tables/overture_layer_audit.csv
outputs/tables/overture_poi_categories.csv
outputs/tables/overture_land_use_classes.csv
outputs/maps/urban_atlas.html
outputs/maps/urban_atlas_preview.png
outputs/tables/urban_atlas_summary.json
outputs/tables/urban_atlas_cells.csv
```

The published maps, previews, and summaries are versioned as a reproducible pilot
snapshot; the downloaded and processed geospatial datasets remain ignored by Git.
OpenStreetMap-derived outputs retain attribution: © OpenStreetMap contributors,
available under the Open Database License. Overture outputs retain Overture Maps
Foundation attribution and preserve the release identifier used for the snapshot.

## Interpreting “most used” roads

The ranked-intersection and centrality outputs can identify roads and junctions
that are structurally important in the mapped network. They cannot establish the
roads people actually use most. A defensible usage study would need observed
traffic counts, probe speeds, transit ridership, or another time-stamped movement
dataset; those measurements can later be joined to this graph.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the staged plan and
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for data-source rules.
