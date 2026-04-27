# Arizona Mine Tunnel Map

Build screening-grade GIS layers for mapped and inferred Arizona mine tunnel features.

The script queries OpenStreetMap through Overpass for Yavapai County, Santa Cruz County, and the Lone Star Mine area, then exports separate GeoJSON layers plus a layered KMZ.

## Contents

- `build_az_tunnel_portal_layers.py` queries source data, writes tunnel-line, portal, addit, stope-like, inferred-connector GeoJSON layers, and builds a KMZ package.

## Outputs

The script writes to a dated folder under:

```text
/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/
```

Expected layer files:

- `tunnel_lines.geojson`
- `portals.geojson`
- `addits.geojson`
- `stopes_or_stope_like.geojson`
- `inferred_tunnel_connectors.geojson`
- `az_mine_tunnels_portals_addits_stopes_layers.kmz`

Mapped geometries come from OpenStreetMap. Inferred connectors are association visuals only, not surveyed underground alignments.

## Run

```bash
python build_az_tunnel_portal_layers.py
```
