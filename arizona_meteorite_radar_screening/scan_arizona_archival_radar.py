#!/usr/bin/env python3
"""
Arizona NEXRAD meteorite-return screening.

This is a screening tool, not a meteorite classifier. It looks for compact,
transient, non-meteorological dual-pol echoes in Level II radar volumes and
exports centroids for GIS review.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pyart
from pyproj import Geod
from scipy import ndimage


AZ_BOUNDS = (-115.2, 31.2, -108.8, 37.3)  # lon min, lat min, lon max, lat max
AZ_STATIONS = [
    # In-state Arizona WSR-88D sites.
    "KFSX",  # Flagstaff
    "KIWA",  # Phoenix / Mesa Gateway
    "KEMX",  # Tucson
    "KYUX",  # Yuma
    # Neighboring radars with useful coverage into Arizona.
    "KESX",  # Las Vegas, NV
    "KICX",  # Cedar City, UT
    "KABX",  # Albuquerque, NM
    "KFDX",  # Cannon AFB, NM
    "KEPZ",  # El Paso, TX/NM
    "KSOX",  # Santa Ana Mountains, CA
    "KNKX",  # San Diego, CA
    "KVBX",  # Vandenberg, CA
]
S3 = "https://unidata-nexrad-level2.s3.amazonaws.com"
GEOD = Geod(ellps="WGS84")


@dataclass
class RadarFile:
    station: str
    key: str
    dt: datetime
    url: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Screen Arizona NEXRAD Level II archives for meteorite-like returns.")
    p.add_argument("--start-utc", required=True, help="UTC start, e.g. 2026-03-01T07:35:00Z")
    p.add_argument("--end-utc", required=True, help="UTC end, e.g. 2026-03-01T08:45:00Z")
    p.add_argument("--stations", default=",".join(AZ_STATIONS), help="Comma-separated radar station IDs")
    p.add_argument("--outdir", default="/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/arizona_meteorite_radar_screening")
    p.add_argument("--workdir", default="/mnt/c/Users/Cobiwan Kenobi/Documents/Codex/arizona_meteorite_radar_screening/cache")
    p.add_argument("--label", default="arizona_archival_screen")
    p.add_argument("--max-files", type=int, default=80)
    p.add_argument("--reflectivity-only", action="store_true",
                   help="Allow pre-dual-pol files with no rhoHV by using reflectivity/size/altitude scoring only.")
    p.add_argument("--delete-cache", action="store_true", help="Delete downloaded radar files after successful scan.")
    return p.parse_args()


def parse_dt(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def list_station_day(station: str, day: datetime) -> list[RadarFile]:
    prefix = f"{day:%Y/%m/%d}/{station}/"
    url = f"{S3}/?list-type=2&prefix={prefix}&max-keys=1000"
    root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
    ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    out: list[RadarFile] = []
    for e in root.findall("s:Contents/s:Key", ns):
        key = e.text or ""
        name = key.rsplit("/", 1)[-1]
        if "_MDM" in name:
            continue
        m = re.search(r"([A-Z0-9]{4})(\d{8})_(\d{6})", name)
        if not m:
            continue
        dt = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        out.append(RadarFile(station, key, dt, f"{S3}/{key}"))
    return out


def list_files(stations: list[str], start: datetime, end: datetime) -> list[RadarFile]:
    days = []
    d = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    files = []
    for st in stations:
        for day in days:
            try:
                files.extend(f for f in list_station_day(st, day) if start <= f.dt <= end)
            except Exception as exc:
                print(f"WARN {st} {day:%Y-%m-%d}: {exc}", flush=True)
    return sorted(files, key=lambda x: (x.dt, x.station))


def download(rf: RadarFile, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / rf.station / rf.key.rsplit("/", 1)[-1]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 100_000:
        return path
    with urllib.request.urlopen(rf.url, timeout=120) as r, open(path, "wb") as w:
        w.write(r.read())
    return path


def scan_volume(path: Path, reflectivity_only: bool = False) -> list[dict]:
    radar = pyart.io.read_nexrad_archive(str(path))
    station = path.name[:4]
    time_utc = path.name[4:12] + "T" + path.name[13:19] + "Z"
    z = radar.fields.get("reflectivity", {}).get("data")
    rho = radar.fields.get("cross_correlation_ratio", {}).get("data")
    sw = radar.fields.get("spectrum_width", {}).get("data")
    vel = radar.fields.get("velocity", {}).get("data")
    if z is None:
        return []
    dual_pol = rho is not None
    if rho is None:
        if not reflectivity_only:
            return []
        rho = np.ma.masked_all(z.shape)
    ranges = radar.range["data"] / 1000.0
    radar_lat = float(radar.latitude["data"][0])
    radar_lon = float(radar.longitude["data"][0])
    radar_alt = float(radar.altitude["data"][0])
    rows = []
    for si in range(min(radar.nsweeps, 14)):
        elev = float(radar.fixed_angle["data"][si])
        if elev < 0.3 or elev > 8.0:
            continue
        a = radar.sweep_start_ray_index["data"][si]
        b = radar.sweep_end_ray_index["data"][si] + 1
        zz = np.ma.filled(z[a:b], np.nan)
        rr = np.ma.filled(rho[a:b], np.nan) if dual_pol else np.full_like(zz, 0.96)
        ss = np.ma.filled(sw[a:b], np.nan) if sw is not None else np.full_like(zz, np.nan)
        vv = np.ma.filled(vel[a:b], np.nan) if vel is not None else np.full_like(zz, np.nan)
        rg = np.broadcast_to(ranges, zz.shape)
        if dual_pol:
            mask = (zz >= 3) & (zz <= 45) & (rr < 0.96) & (rg > 15) & (rg < 260)
        else:
            # Pre-dual-pol mode is intentionally stricter on compactness and
            # altitude because rhoHV is unavailable to reject ordinary weather.
            mask = (zz >= 6) & (zz <= 42) & (rg > 15) & (rg < 220)
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        if n == 0:
            continue
        az = radar.azimuth["data"][a:b]
        for labid in range(1, n + 1):
            inds = np.where(lab == labid)
            cnt = len(inds[0])
            max_pixels = 90 if not dual_pol else 250
            if cnt < 3 or cnt > max_pixels:
                continue
            az_rad = np.deg2rad(az[inds[0]])
            caz = (math.degrees(math.atan2(np.nanmean(np.sin(az_rad)), np.nanmean(np.cos(az_rad)))) + 360) % 360
            crange = float(np.nanmean(rg[inds]))
            ground = crange * math.cos(math.radians(elev))
            lon, lat, _ = GEOD.fwd(radar_lon, radar_lat, caz, ground * 1000.0)
            alt = radar_alt + crange * 1000.0 * math.sin(math.radians(elev)) + ((ground * 1000.0) ** 2 / (2 * 6371000.0))
            if not (AZ_BOUNDS[0] <= lon <= AZ_BOUNDS[2] and AZ_BOUNDS[1] <= lat <= AZ_BOUNDS[3] and 1000 <= alt <= 16000):
                continue
            zmean = float(np.nanmean(zz[inds]))
            rmean = float(np.nanmean(rr[inds]))
            swmean = float(np.nanmean(ss[inds]))
            vstd = float(np.nanstd(vv[inds]))
            if math.isnan(swmean):
                swmean = 0.0
            if math.isnan(vstd):
                vstd = 0.0
            if dual_pol:
                score = zmean / 10.0 + max(0, 0.96 - rmean) * 4.0 + min(max(swmean, 0), 10) / 10.0 + min(max(vstd, 0), 15) / 15.0
                mode = "dual_pol"
            else:
                compact_bonus = max(0, 1.0 - (cnt / 90.0))
                altitude_bonus = 1.0 if 2500 <= alt <= 10000 else 0.0
                score = zmean / 10.0 + compact_bonus + altitude_bonus
                mode = "reflectivity_only_pre_dualpol"
            rows.append({
                "station": station,
                "time_utc": time_utc,
                "sweep": si,
                "elev_deg": round(elev, 3),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "alt_m_asl": round(alt, 1),
                "range_km": round(crange, 2),
                "pixel_count": int(cnt),
                "z_mean": round(zmean, 2),
                "z_max": round(float(np.nanmax(zz[inds])), 2),
                "rho_mean": round(rmean, 3),
                "sw_mean": round(swmean, 2),
                "vel_std": round(vstd, 2),
                "score": round(score, 3),
                "scan_mode": mode,
                "classification": "candidate_compact_nonweather_echo",
                "caution": "screening only; radar centroid is not a confirmed meteorite location",
            })
    return rows


def write_geojson(rows: list[dict], path: Path):
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"], r["alt_m_asl"]]},
        "properties": {**r, "rank": i + 1},
    } for i, r in enumerate(rows)]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))


def write_kmz(rows: list[dict], path: Path):
    kml = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
           "<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>",
           "<name>Arizona archival radar meteorite screening</name>"]
    for i, r in enumerate(rows, 1):
        desc = "<br/>".join(f"{k}: {v}" for k, v in r.items())
        color = "ff0000ff" if i <= 25 else "ff00ffff"
        kml.append(f"<Placemark><name>{i} {r['station']} {r['time_utc']} score {r['score']}</name>"
                   f"<description><![CDATA[{desc}]]></description>"
                   f"<Style><IconStyle><color>{color}</color><scale>0.9</scale>"
                   f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>"
                   f"</IconStyle></Style>"
                   f"<Point><altitudeMode>absolute</altitudeMode><coordinates>{r['lon']},{r['lat']},{r['alt_m_asl']}</coordinates></Point></Placemark>")
    kml.append("</Document></kml>")
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("doc.kml", "\n".join(kml))


def main():
    args = parse_args()
    start = parse_dt(args.start_utc)
    end = parse_dt(args.end_utc)
    stations = [s.strip().upper() for s in args.stations.split(",") if s.strip()]
    outdir = Path(args.outdir)
    workdir = Path(args.workdir)
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_files(stations, start, end)[: args.max_files]
    print(f"selected_files={len(files)}", flush=True)
    rows = []
    manifest = []
    for rf in files:
        print(f"download/scan {rf.station} {rf.dt.isoformat()}", flush=True)
        path = download(rf, workdir)
        manifest.append({"station": rf.station, "datetime_utc": rf.dt.isoformat(), "key": rf.key})
        try:
            rows.extend(scan_volume(path, reflectivity_only=args.reflectivity_only))
            if args.delete_cache:
                path.unlink(missing_ok=True)
        except Exception as exc:
            print(f"WARN scan failed {path.name}: {exc}", flush=True)
    rows.sort(key=lambda r: (-r["score"], r["time_utc"], r["station"]))
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.label)
    csv_path = outdir / f"{label}_candidates.csv"
    geo_path = outdir / f"{label}_candidates.geojson"
    kmz_path = outdir / f"{label}_candidates.kmz"
    summary_path = outdir / f"{label}_summary.json"
    with csv_path.open("w", newline="") as fp:
        fieldnames = list(rows[0].keys()) if rows else ["station", "time_utc"]
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    write_geojson(rows[:500], geo_path)
    write_kmz(rows[:500], kmz_path)
    summary_path.write_text(json.dumps({
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "stations": stations,
        "files_scanned": len(files),
        "candidate_rows": len(rows),
        "outputs": {"csv": str(csv_path), "geojson": str(geo_path), "kmz": str(kmz_path)},
        "manifest": manifest,
    }, indent=2))
    print(csv_path)
    print(geo_path)
    print(kmz_path)
    print(summary_path)
    print(f"candidate_rows={len(rows)}")


if __name__ == "__main__":
    main()
