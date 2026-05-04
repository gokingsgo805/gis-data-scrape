#!/usr/bin/env python3
"""Build a live BLM active-claim status layer around mine points."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from arizona_common import BLM_CLAIMS_URL, TYPE_LABELS, envelope, make_kmz, polygon_kml, query_url, request_json, write_geojson

BUILD_DATE = "2026-05-03"
FIELDS = (
    "OBJECTID,ADMIN_STATE,GEO_STATE,BLM_PROD,CSE_DISP,CSE_TYPE_NR,CSE_NR,"
    "LEG_CSE_NR,CSE_NAME,SRC,QLTY,CSE_META,RCRD_ACRS,SF_ID,REC_TYPE_CSE_GRP,"
    "MC_PATENTED,MC_EXCLUDED,MC_CONVEYED"
)


def query_active_claims(lon: float, lat: float, radius_miles: float) -> list[dict]:
    params = {
        "f": "geojson",
        "where": "1=1",
        "geometry": json.dumps(envelope(lon, lat, radius_miles), separators=(",", ":")),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": "2000",
    }
    url = query_url(f"{BLM_CLAIMS_URL}/1/query", params)
    last_error = None
    for attempt in range(6):
        try:
            data = request_json(url, timeout=180)
            if "error" in data:
                raise RuntimeError(data["error"])
            return data.get("features", [])
        except Exception as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(str(last_error))


def claim_key(feature: dict) -> str:
    props = feature.get("properties", {})
    return str(props.get("OBJECTID") or props.get("CSE_NR") or props.get("LEG_CSE_NR") or id(feature))


def claim_example(feature: dict) -> str:
    props = feature["properties"]
    parts = []
    for key in ["CSE_NAME", "CSE_NR", "CSE_DISP", "claim_type_label", "RCRD_ACRS", "MC_PATENTED"]:
        value = props.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    return " | ".join(map(str, parts))


def as_float(value):
    try:
        return float(value)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mine-points", required=True)
    parser.add_argument("--out", default="az_live_claim_status")
    parser.add_argument("--radius-miles", type=float, default=1.0)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mines = json.loads(Path(args.mine_points).read_text(encoding="utf-8"))["features"]

    boundary_by_key = {}
    active_by_mine = defaultdict(list)
    query_errors = {}
    for index, mine in enumerate(mines, 1):
        props = mine["properties"]
        dep_id = props.get("mrds_dep_id")
        lon, lat = mine["geometry"]["coordinates"][:2]
        try:
            claims = query_active_claims(lon, lat, args.radius_miles)
        except Exception as exc:
            query_errors[dep_id] = str(exc)
            continue
        for claim in claims:
            claim_props = dict(claim.get("properties", {}))
            key = claim_key({"properties": claim_props})
            active_by_mine[dep_id].append(key)
            if key not in boundary_by_key:
                claim_props["claim_type_label"] = TYPE_LABELS.get(str(claim_props.get("CSE_TYPE_NR")), str(claim_props.get("CSE_TYPE_NR") or "Unknown"))
                claim_props["recorded_claim_acres"] = claim_props.get("RCRD_ACRS")
                claim_props["matched_mrds_dep_ids"] = dep_id or ""
                claim_props["matched_mine_names"] = props.get("name") or ""
                claim_props["live_status_query_date"] = BUILD_DATE
                claim_props["screening_radius_miles"] = args.radius_miles
                claim_props["claim_boundary_caution"] = "Screening only; BLM claim geometry may not be exact staked boundaries."
                claim["properties"] = claim_props
                boundary_by_key[key] = claim
        print(f"{index}/{len(mines)} {props.get('name')}: {len(claims)} live active claims")

    boundaries = list(boundary_by_key.values())
    live_points = []
    for mine in mines:
        props = mine["properties"]
        dep_id = props.get("mrds_dep_id")
        claims = [boundary_by_key[key] for key in active_by_mine.get(dep_id, []) if key in boundary_by_key]
        acres = [as_float(claim["properties"].get("RCRD_ACRS")) for claim in claims]
        acres = [value for value in acres if value is not None]
        dispositions = Counter(str(claim["properties"].get("CSE_DISP") or "Unknown") for claim in claims)
        types = Counter(str(claim["properties"].get("claim_type_label") or "Unknown") for claim in claims)
        new_props = {
            "name": props.get("name"),
            "county": props.get("county"),
            "district": props.get("district"),
            "mrds_dep_id": dep_id,
            "mrds_url": props.get("mrds_url"),
            "live_current_claim_status": "LIVE_ACTIVE_BLM_CLAIMS_WITHIN_SCREEN" if claims else ("LIVE_CLAIM_QUERY_ERROR" if dep_id in query_errors else "NO_LIVE_ACTIVE_BLM_CLAIMS_FOUND_WITHIN_SCREEN"),
            "live_active_claim_boundary_count": len(claims),
            "live_active_claim_dispositions": "; ".join(f"{key}: {value}" for key, value in dispositions.most_common()),
            "live_active_claim_types": "; ".join(f"{key}: {value}" for key, value in types.most_common()),
            "live_active_claim_acres_total": round(sum(acres), 3) if acres else 0,
            "live_active_claim_acres_max": round(max(acres), 3) if acres else "",
            "live_active_claim_examples": "; ".join(claim_example(claim) for claim in claims[:12]),
            "live_query_error": query_errors.get(dep_id, ""),
            "claim_status_caution": "Live GIS screening only; verify MLRS, county records, patents/private land, withdrawals, access, and monuments.",
        }
        live_points.append({"type": "Feature", "geometry": mine["geometry"], "properties": new_props})

    write_geojson(out_dir / "az_live_claim_status_mine_points.geojson", live_points, "az_live_claim_status_mine_points", BUILD_DATE)
    write_geojson(out_dir / "az_live_active_claim_boundaries.geojson", boundaries, "az_live_active_claim_boundaries", BUILD_DATE)
    with (out_dir / "az_live_claim_status_per_mine.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(live_points[0]["properties"].keys()) if live_points else []
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for feature in live_points:
            writer.writerow(feature["properties"])

    placemarks = []
    for mine in live_points:
        lon, lat = mine["geometry"]["coordinates"][:2]
        props = mine["properties"]
        rows = "".join(f"<tr><th>{key}</th><td>{props.get(key, '')}</td></tr>" for key in props)
        placemarks.append(f"<Placemark><name>{props.get('name')}</name><description><![CDATA[<table>{rows}</table>]]></description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>")
    for claim in boundaries:
        props = claim["properties"]
        rows = "".join(f"<tr><th>{key}</th><td>{props.get(key, '')}</td></tr>" for key in props)
        placemarks.append(f"<Placemark><name>{props.get('CSE_NAME') or props.get('CSE_NR')}</name><description><![CDATA[<table>{rows}</table>]]></description>{polygon_kml(claim.get('geometry'))}</Placemark>")
    kml_path = out_dir / "az_live_claim_status_layer.kml"
    kml_path.write_text('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + "".join(placemarks) + "</Document></kml>", encoding="utf-8")
    make_kmz(kml_path, out_dir / "az_live_claim_status_layer.kmz")

    summary = {
        "generated": BUILD_DATE,
        "mine_points": len(live_points),
        "unique_live_active_claim_boundaries": len(boundaries),
        "status_counts": dict(Counter(feature["properties"]["live_current_claim_status"] for feature in live_points)),
        "query_errors": query_errors,
    }
    (out_dir / "build_summary_live_claim_status.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
