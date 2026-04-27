#!/usr/bin/env bash
set -u

COMMAND_FILE="${1:?usage: run_scan_command_file.sh command_file}"
OUTDIR="/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/arizona_meteorite_radar_screening"

while IFS= read -r cmd; do
  [[ -z "$cmd" || "$cmd" == \#* ]] && continue
  [[ "$cmd" == "set -u" || "$cmd" == "set -e"* || "$cmd" == "#!"* ]] && continue
  label="$(sed -n 's/.*--label \([^ ]*\).*/\1/p' <<<"$cmd")"
  if [[ -n "$label" && -s "$OUTDIR/${label}_summary.json" ]]; then
    echo "SKIP completed $label"
    continue
  fi
  echo "RUN $label"
  date -u +"START %Y-%m-%dT%H:%M:%SZ"
  bash -lc "$cmd"
  status=$?
  date -u +"END %Y-%m-%dT%H:%M:%SZ status=$status"
  if [[ $status -ne 0 ]]; then
    echo "FAILED $label status=$status"
  fi
done < "$COMMAND_FILE"
