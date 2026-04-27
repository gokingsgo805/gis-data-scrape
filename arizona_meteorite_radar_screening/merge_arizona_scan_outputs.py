#!/usr/bin/env python3
"""Merge Arizona radar-screening chunk CSVs into statewide GeoJSON/KMZ layers."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


OUTDIR = Path("/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/arizona_meteorite_radar_screening")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--indir", default=str(OUTDIR))
    p.add_argument("--prefix", default="az_nexrad_meteorite_screen_")
    p.add_argument("--label", default="az_nexrad_meteorite_screen_merged")
    p.add_argument("--top", type=int, default=2000)
    p.add_argument("--min-score", type=float, default=4.0)
    return p.parse_args()


def write_geojson(rows, path):
    features = []
    for i, r in enumerate(rows, 1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"]), float(r["alt_m_asl"])]},
            "properties": {**r, "rank": i},
        })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))


def write_kmz(rows, path):
    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        "<name>Arizona historical NEXRAD meteorite-return screening</name>",
    ]
    for i, r in enumerate(rows, 1):
        desc = "<br/>".join(f"{k}: {v}" for k, v in r.items())
        color = "ff0000ff" if i <= 100 else "ff00ffff"
        kml.append(
            f"<Placemark><name>{i} {r.get('station','')} {r.get('time_utc','')} score {r.get('score','')}</name>"
            f"<description><![CDATA[{desc}]]></description>"
            f"<Style><IconStyle><color>{color}</color><scale>0.85</scale>"
            f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>"
            f"</IconStyle></Style>"
            f"<Point><altitudeMode>absolute</altitudeMode><coordinates>{r['lon']},{r['lat']},{r['alt_m_asl']}</coordinates></Point></Placemark>"
        )
    kml.append("</Document></kml>")
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("doc.kml", "\n".join(kml))


def main():
    args = parse_args()
    indir = Path(args.indir)
    rows = []
    for path in sorted(indir.glob(f"{args.prefix}*_candidates.csv")):
        with path.open(newline="") as fp:
            for r in csv.DictReader(fp):
                try:
                    score = float(r.get("score", "nan"))
                    float(r["lat"]); float(r["lon"]); float(r["alt_m_asl"])
                except Exception:
                    continue
                if score >= args.min_score:
                    r["source_csv"] = path.name
                    rows.append(r)
    rows.sort(key=lambda r: (-float(r["score"]), r.get("time_utc", ""), r.get("station", "")))
    rows = rows[: args.top]
    csv_path = indir / f"{args.label}_top{len(rows)}.csv"
    geo_path = indir / f"{args.label}_top{len(rows)}.geojson"
    kmz_path = indir / f"{args.label}_top{len(rows)}.kmz"
    if rows:
        with csv_path.open("w", newline="") as fp:
            fields = list(rows[0].keys())
            w = csv.DictWriter(fp, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    write_geojson(rows, geo_path)
    write_kmz(rows, kmz_path)
    print(csv_path)
    print(geo_path)
    print(kmz_path)
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
