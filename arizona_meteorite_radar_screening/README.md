# Arizona Meteorite Radar Screening

Screen Arizona NEXRAD Level II radar archives for compact, transient echoes that may be worth follow-up GIS review.

This is a screening tool, not a meteorite classifier or field-confirmed fall map. Outputs are candidate centroids for review in QGIS or Google Earth.

## Contents

- `scan_arizona_archival_radar.py` downloads selected NEXRAD Level II volumes, scores compact non-weather-like echoes, and exports CSV, GeoJSON, KMZ, and summary JSON.
- `build_arizona_historical_scan_plan.py` generates chunked shell command lists for longer scans.
- `merge_arizona_scan_outputs.py` merges scan outputs from chunked runs.
- `run_scan_command_file.sh` runs command lists safely.
- `test_one_command.sh` is a small smoke-test command.

Generated command lists, logs, PID files, and cached radar volumes are intentionally ignored. Regenerate command lists from `build_arizona_historical_scan_plan.py`.

## Requirements

Python packages used by the scanner:

- `arm_pyart`
- `numpy`
- `pyproj`
- `scipy`

## Example

```bash
python scan_arizona_archival_radar.py \
  --start-utc 2026-03-01T07:35:00Z \
  --end-utc 2026-03-01T08:45:00Z \
  --stations KFSX,KIWA,KEMX,KYUX \
  --label az_test_window
```

For older pre-dual-pol scans, add `--reflectivity-only`.
