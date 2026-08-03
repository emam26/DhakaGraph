# Expanded study area

The default study is a fixed polygon designed to cover the requested
Airport-Uttara-Sayedabad north-south span, all of Mirpur, and the eastern
Gulshan-Badda-Bashundhara area. A fixed polygon makes repeated OpenStreetMap
downloads comparable and avoids relying on changing place-name search boundaries.

## Requested anchors

The following OpenStreetMap geocoder results were checked on 2026-08-04. They
are validation anchors, not the polygon vertices.

| Anchor | Latitude | Longitude |
| --- | ---: | ---: |
| Hazrat Shahjalal International Airport | 23.8431441 | 90.4053032 |
| Uttara | 23.8693275 | 90.3926893 |
| Mirpur | 23.8123629 | 90.3640891 |
| Gulshan 2 Circle | 23.7948921 | 90.4138705 |
| Badda | 23.7765425 | 90.4463012 |
| Bashundhara Residential Area | 23.8189265 | 90.4368229 |
| Sayedabad Bus Terminal | 23.7153498 | 90.4275444 |

Automated tests verify that all seven anchors lie inside the configured polygon.

## Polygon vertices

Coordinates use WGS 84 longitude/latitude order, as required by Shapely and
OSMnx.

| Vertex | Longitude | Latitude |
| ---: | ---: | ---: |
| 1 | 90.312 | 23.765 |
| 2 | 90.312 | 23.840 |
| 3 | 90.338 | 23.900 |
| 4 | 90.470 | 23.900 |
| 5 | 90.486 | 23.815 |
| 6 | 90.478 | 23.755 |
| 7 | 90.455 | 23.695 |
| 8 | 90.398 | 23.695 |
| 9 | 90.352 | 23.730 |

The boundary intentionally includes a modest margin around the named anchors.
It is a project study boundary, not an administrative definition of Dhaka or
any included neighborhood.
