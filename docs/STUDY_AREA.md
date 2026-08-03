# Expanded study area

The default study is a fixed polygon designed to cover the requested
Airport-Uttara-Sayedabad north-south span and all of Mirpur. A fixed polygon
makes repeated OpenStreetMap downloads comparable and avoids relying on changing
place-name search boundaries.

## Requested anchors

The following OpenStreetMap geocoder results were checked on 2026-08-04. They
are validation anchors, not the polygon vertices.

| Anchor | Latitude | Longitude |
| --- | ---: | ---: |
| Hazrat Shahjalal International Airport | 23.8431441 | 90.4053032 |
| Uttara | 23.8693275 | 90.3926893 |
| Mirpur | 23.8123629 | 90.3640891 |
| Sayedabad Bus Terminal | 23.7153498 | 90.4275444 |

Automated tests verify that all four anchors lie inside the configured polygon.

## Polygon vertices

Coordinates use WGS 84 longitude/latitude order, as required by Shapely and
OSMnx.

| Vertex | Longitude | Latitude |
| ---: | ---: | ---: |
| 1 | 90.312 | 23.765 |
| 2 | 90.312 | 23.840 |
| 3 | 90.338 | 23.900 |
| 4 | 90.442 | 23.900 |
| 5 | 90.442 | 23.695 |
| 6 | 90.398 | 23.695 |
| 7 | 90.352 | 23.730 |

The boundary intentionally includes a modest margin around the named anchors.
It is a project study boundary, not an administrative definition of Dhaka,
Uttara, or Mirpur.
