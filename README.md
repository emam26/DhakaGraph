# DhakaGraph

DhakaGraph is a learning-oriented exploration of Dhaka as a spatial graph. The
project begins with roads and intersections, then adds places, public transport,
and flood scenarios as the underlying data are audited.

The first milestone builds a drive network within 2.5 km of Shahbag from
OpenStreetMap, converts it through City2Graph, calculates structural network
metrics, and writes an interactive map. These metrics describe map connectivity;
they are not measurements of live Dhaka traffic.

## Current milestone

- Download and cache a small central-Dhaka road graph.
- Convert the OSMnx graph through City2Graph.
- Measure graph size, connectivity, and approximate node betweenness.
- Export ranked intersections, a summary, processed spatial layers, and an HTML map.
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
dhakagraph-pilot --radius 1500 --centrality-samples 200 --top-n 25
dhakagraph-pilot --refresh
```

The first run needs internet access to query OpenStreetMap. Later runs reuse
the cached GraphML file unless `--refresh` is supplied.

## Outputs

```text
data/raw/central_dhaka_shahbag_drive.graphml
data/processed/central_dhaka_shahbag_nodes.geojson
data/processed/central_dhaka_shahbag_edges.geojson
outputs/tables/network_summary.json
outputs/tables/top_intersections.csv
outputs/maps/centrality_map.html
outputs/maps/centrality_preview.png
```

Generated data and maps are intentionally ignored by Git. OpenStreetMap-derived
outputs must retain attribution: © OpenStreetMap contributors, available under
the Open Database License.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the staged plan and
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for data-source rules.
