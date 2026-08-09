# DhakaGraph output catalog

All published visualizations are stored in `outputs/maps/`. Their supporting
tables and interpretation summaries are stored in `outputs/tables/`. The
interactive HTML pages are also available through the [GitHub Pages site](https://emam26.github.io/DhakaGraph/).

## Published visualizations

| Study | Main question | Interactive map | Preview | Supporting outcomes |
| --- | --- | --- | --- | --- |
| Dhaka heterogeneous graph | How do mapped roads, buildings, cells, and cross-layer relations fit together? | [Graph explorer](https://emam26.github.io/DhakaGraph/outputs/maps/network_explorer.html) | [Dhaka graph thumbnail](../outputs/maps/network_graph_thumbnail.png) | [Network summary](../outputs/tables/network_summary.json) |
| Structural network | Which mapped road nodes are structurally central? | [Centrality map](https://emam26.github.io/DhakaGraph/outputs/maps/centrality_map.html) | [Centrality preview](../outputs/maps/centrality_preview.png) | [Top intersections](../outputs/tables/top_intersections.csv) |
| Overture coverage | What mapped buildings, places, roads, water, and land use are available? | [Overture explorer](https://emam26.github.io/DhakaGraph/outputs/maps/overture_explorer.html) | [Overture preview](../outputs/maps/overture_preview.png) | [Layer audit](../outputs/tables/overture_layer_audit.csv) |
| Urban function atlas | What recurring mapped urban patterns appear across 750 m cells? | [Urban atlas](https://emam26.github.io/DhakaGraph/outputs/maps/urban_atlas.html) | [Atlas preview](../outputs/maps/urban_atlas_preview.png) | [Atlas cells](../outputs/tables/urban_atlas_cells.csv) |
| Service accessibility | Where are mapped education, healthcare, markets, parks, and transport facilities farther away? | [Service access](https://emam26.github.io/DhakaGraph/outputs/maps/service_accessibility.html) | [Access preview](../outputs/maps/service_accessibility_preview.png) | [Service deserts](../outputs/tables/service_deserts.csv) |
| Neighborhood similarity | Which cells have a similar mapped profile to Airport, Uttara, Mirpur, Gulshan, Badda, Bashundhara, or Sayedabad? | [Similarity explorer](https://emam26.github.io/DhakaGraph/outputs/maps/neighborhood_similarity.html) | [Similarity preview](../outputs/maps/neighborhood_similarity_preview.png) | [Similarity rankings](../outputs/tables/neighborhood_similarity_rankings.csv) |
| Flood resilience | How does the connector-split road graph respond to modeled water levels? | [Flood scenarios](https://emam26.github.io/DhakaGraph/outputs/maps/flood_simulation.html) | [Flood preview](../outputs/maps/flood_simulation_preview.png) | [Flood summary](../outputs/tables/flood_cascade_summary.json) |
| Population-weighted equity | Which service gaps affect more of the mapped population proxy? | [Service equity](https://emam26.github.io/DhakaGraph/outputs/maps/population_equity.html) | [Equity preview](../outputs/maps/population_equity_preview.png) | [Equity rankings](../outputs/tables/population_equity_rankings.csv) |
| Modeled mobility pressure | Which roads and intersections repeatedly appear in modeled origin-destination routes? | [Mobility pressure](https://emam26.github.io/DhakaGraph/outputs/maps/mobility_pressure.html) | [Mobility preview](../outputs/maps/mobility_pressure_preview.png) | [Pressure roads](../outputs/tables/mobility_pressure_top.csv) |
| Heat, air, and green space | Where do modeled environmental burdens overlap? | [Environmental screen](https://emam26.github.io/DhakaGraph/outputs/maps/environmental_screen.html) | [Environmental preview](../outputs/maps/environmental_screen_preview.png) | [Environmental rankings](../outputs/tables/environmental_burden_top.csv) |
| Compound urban stress | Where do service need, environmental burden, mobility pressure, and flood disruption overlap? | [Compound hotspots](https://emam26.github.io/DhakaGraph/outputs/maps/compound_stress.html) | [Compound preview](../outputs/maps/compound_stress_preview.png) | [Hotspot rankings](../outputs/tables/compound_stress_hotspots.csv) |

## Repository structure

```text
outputs/
├── maps/       published HTML explorers and README-ready PNG previews
└── tables/     cell-level CSVs, ranked shortlists, and JSON summaries
docs/
├── DATA_SOURCES.md
├── OUTPUTS.md
├── ROADMAP.md
└── STUDY_AREA.md
src/dhakagraph/  reproducible acquisition, analysis, mapping, and CLI modules
tests/            unit tests for the analysis modules
```

The raw and processed Overture/OSM caches under `data/` are intentionally not
published as part of the output catalog. They can be regenerated using the
documented pipelines. Temporary browser QA screenshots are also kept ignored;
only the official previews listed above are published.

## Interpretation rule

These outputs describe mapped coverage and transparent modeling experiments.
They are not observed traffic, official flood maps, census counts, measured
air pollution, measured temperature, service quality, or health outcomes.
