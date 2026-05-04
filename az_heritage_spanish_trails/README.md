# Arizona Heritage And Spanish Trail GIS Package

Public-reference GIS package for Arizona managed Indigenous heritage sites,
Spanish colonial public sites, and Arizona portions of the Old Spanish and
Juan Bautista de Anza National Historic Trails.

This package intentionally uses public-facing visitor points, parks, monuments,
and official trail datasets. It does not publish obscure archaeological
coordinates or site-discovery targets.

## Outputs

- `output/az_public_indigenous_heritage_sites.geojson`
- `output/az_spanish_colonial_sites.geojson`
- `output/az_old_spanish_nht_arizona.geojson`
- `output/az_anza_nht_arizona.geojson`
- `output/az_heritage_spanish_trails_bundle.geojson`
- `output/*.kmz`

## Build

```bash
python3 build_az_heritage_spanish_trails.py
```

The script reads the NPS/ArcGIS trail feature services live and writes KMZ and
GeoJSON files to `output/`.
