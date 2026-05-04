# Arizona Gold GIS Screening Scripts

This folder contains reproducible Python scripts for the Arizona gold GIS workflow built in Codex.

Workflows covered:

- Pull Arizona MRDS records from the USGS MRDS OGC FeatureServer.
- Screen Arizona gold records and WWII-window past-producing gold mines.
- Query BLM MLRS/NLSDB live active mining-claim polygons near mine points.
- Export claim status, claim boundaries, claim acreage, patent-field screens, underground-workings screens, GeoJSON, CSV, KML, and KMZ.
- Build statewide predictive gold target layers from all Arizona MRDS gold records.

The main script is `arizona_gold_gis_pipeline.py`.

## Requirements

Python 3.10+ using only the standard library.

## Examples

```bash
python3 arizona_gold_gis_pipeline.py fetch-mrds --out ./az_gold_outputs
python3 arizona_gold_gis_pipeline.py ww2-screen --raw ./az_gold_outputs/mrds_arizona_raw.geojson --out ./az_gold_outputs
python3 arizona_gold_gis_pipeline.py live-claims --mine-points ./az_gold_outputs/az_ww2_shutdown_never_reopened_gold_mines_all_screened.geojson --out ./az_live_claim_status
python3 arizona_gold_gis_pipeline.py predict-statewide --raw ./az_gold_outputs/mrds_arizona_raw.geojson --out ./az_statewide_gold_predictions
```

## Source Services

- USGS MRDS OGC FeatureServer: `https://energy.usgs.gov/arcgis/rest/services/MRData/Mineral_Resource_Data_System/OGCFeatureServer/collections/3/items`
- BLM MLRS/NLSDB Mining Claims MapServer: `https://gis.blm.gov/nlsdb/rest/services/Mining_Claims/MiningClaims/MapServer`

## Caution

These are screening tools only. They do not prove gold is present and do not determine claimability, land status, access rights, patent/private ownership, withdrawals, or safety. BLM claim polygons are often derived from PLSS/legal descriptions and may not represent exact staked claim corners. Verify results in MLRS, county recorder records, BLM land-status records, patents/private parcel data, withdrawals, surface-management rules, and field monuments before acting.
