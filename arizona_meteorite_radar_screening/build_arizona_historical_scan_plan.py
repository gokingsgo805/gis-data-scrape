#!/usr/bin/env python3
"""Build chunked commands for a long Arizona archival NEXRAD meteorite scan."""

from __future__ import annotations

import argparse
import calendar
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_STATIONS = "KFSX,KIWA,KEMX,KYUX,KESX,KICX,KABX,KFDX,KEPZ,KSOX,KNKX,KVBX"
BASE = Path("/mnt/c/Users/Cobiwan Kenobi/Documents/Codex/arizona_meteorite_radar_screening")
SCANNER = BASE / "scan_arizona_archival_radar.py"
PY = "/tmp/radarenv/bin/python"


def parse_args():
    p = argparse.ArgumentParser(description="Create monthly scan command list for Arizona archival radar screening.")
    p.add_argument("--start-year", type=int, default=1991)
    p.add_argument("--end-year", type=int, default=datetime.now(timezone.utc).year)
    p.add_argument("--start-month", type=int, default=1)
    p.add_argument("--end-month", type=int, default=12)
    p.add_argument("--stations", default=DEFAULT_STATIONS)
    p.add_argument("--out", default=str(BASE / "arizona_1995_present_monthly_scan_commands.sh"))
    p.add_argument("--max-files", type=int, default=999999)
    p.add_argument("--delete-cache", action="store_true", default=True)
    p.add_argument("--granularity", choices=["month", "day", "station-day", "station-window"], default="month")
    p.add_argument("--hours-per-window", type=int, default=3)
    return p.parse_args()


def main():
    args = parse_args()
    lines = [
        "#!/usr/bin/env bash",
        "set -u",
        "",
        "# Generated chunk plan. Run one line, a year, or the whole file.",
        "# Outputs land in: /mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/arizona_meteorite_radar_screening",
        "",
    ]
    stations = [s.strip().upper() for s in args.stations.split(",") if s.strip()]

    def add_cmd(start_dt: datetime, end_dt: datetime, label: str, station_arg: str):
        cmd = [
            PY,
            str(SCANNER),
            "--start-utc", start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "--end-utc", end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "--stations", station_arg,
            "--label", label,
            "--max-files", str(args.max_files),
        ]
        if start_dt.year < 2014:
            cmd.append("--reflectivity-only")
        if args.delete_cache:
            cmd.append("--delete-cache")
        lines.append(" ".join(shlex.quote(part) for part in cmd))

    start_date = datetime(args.start_year, args.start_month, 1, tzinfo=timezone.utc)
    end_last = calendar.monthrange(args.end_year, args.end_month)[1]
    end_date = datetime(args.end_year, args.end_month, end_last, 23, 59, 59, tzinfo=timezone.utc)
    if args.granularity == "month":
        year, month = args.start_year, args.start_month
        while (year, month) <= (args.end_year, args.end_month):
            last = calendar.monthrange(year, month)[1]
            start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
            end_dt = datetime(year, month, last, 23, 59, 59, tzinfo=timezone.utc)
            add_cmd(start_dt, end_dt, f"az_nexrad_meteorite_screen_{year:04d}_{month:02d}", args.stations)
            month += 1
            if month == 13:
                year += 1
                month = 1
    elif args.granularity in ("day", "station-day"):
        d = start_date
        while d <= end_date:
            day_end = d.replace(hour=23, minute=59, second=59)
            if args.granularity == "day":
                add_cmd(d, day_end, f"az_nexrad_meteorite_screen_{d:%Y_%m_%d}", args.stations)
            else:
                for st in stations:
                    add_cmd(d, day_end, f"az_nexrad_meteorite_screen_{d:%Y_%m_%d}_{st}", st)
            d += timedelta(days=1)
    else:
        d = start_date
        while d <= end_date:
            for st in stations:
                block_start = d
                while block_start.date() == d.date():
                    block_end = min(
                        block_start + timedelta(hours=args.hours_per_window) - timedelta(seconds=1),
                        d.replace(hour=23, minute=59, second=59),
                    )
                    add_cmd(
                        block_start,
                        block_end,
                        f"az_nexrad_meteorite_screen_{block_start:%Y_%m_%d_%H}_{st}",
                        st,
                    )
                    block_start += timedelta(hours=args.hours_per_window)
            d += timedelta(days=1)
    out = Path(args.out)
    out.write_text("\n".join(lines) + "\n")
    out.chmod(0o755)
    print(out)
    print(f"commands={len(lines) - 6}")


if __name__ == "__main__":
    main()
