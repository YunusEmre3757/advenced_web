Place the real active fault lines GeoJSON file here:

- Path: `backend/src/main/resources/data/turkey_active_faults.geojson`
- Required root: `FeatureCollection`
- Geometry types: `LineString` or `MultiLineString`

Alternative:

- Set `faults.mta.geojson-path` in `application.properties` to an absolute file path.

Backend endpoint:

- `GET /api/fault-lines`

---

Place the real soil site-class GeoJSON file here:

- Path: `backend/src/main/resources/data/turkey_soil_site_classes.geojson`
- Required root: `FeatureCollection`
- Geometry types: `Polygon` or `MultiPolygon`
- Recommended properties:
  - `siteClass` (values: `ZA`, `ZB`, `ZC`, `ZD`, `ZE`, `ZF`)
  - or `vs30` (service maps it to `siteClass`)

Alternative:

- Set `soil.zones.geojson-path` in `application.properties` to an absolute file path.

Backend endpoint:

- `GET /api/soil-zones`
