# Arizona Gold GIS Screening Scripts

These scripts reproduce the Arizona gold GIS layers generated in Codex:

- MRDS statewide Arizona gold screening.
- WWII-window past-producer gold mine screening.
- BLM MLRS/NLSDB live active-claim status layers.
- Claim boundary, acreage, patent-field, and underground-workings summaries.
- Statewide predicted gold target layers.

The scripts are screening tools only. They do not prove gold is present and do
not determine claimability, land status, access rights, patent/private land, or
safety. Verify results in MLRS, county recorder records, BLM land-status
records, patents/private parcel data, withdrawals, surface-management rules,
and field monuments before acting.

## Requirements

Python 3.10+ using only the standard library.

## Quick Start

```bash
python3 arizona_gold_pipeline.py --out "./az_gold_outputs"
python3 arizona_live_claim_status.py --mine-points "./az_gold_outputs/az_ww2_shutdown_never_reopened_gold_mines_all_screened.geojson" --out "./az_live_claim_status"
python3 arizona_statewide_gold_predictions.py --raw-mrds "./az_gold_outputs/mrds_arizona_raw.geojson" --out "./az_statewide_gold_predictions"
```

The output folders include GeoJSON, KML/KMZ, CSV, README, and build-summary
files.

## Source Services

- USGS MRDS OGC FeatureServer:
  `https://energy.usgs.gov/arcgis/rest/services/MRData/Mineral_Resource_Data_System/OGCFeatureServer/collections/3/items`
- BLM MLRS/NLSDB Mining Claims MapServer:
  `https://gis.blm.gov/nlsdb/rest/services/Mining_Claims/MiningClaims/MapServer`

## Notes

BLM claim polygons are often derived from PLSS/legal descriptions and may not
represent exact staked claim corners. The `MC_PATENTED` field being blank does
not prove that no patented/private land exists.
