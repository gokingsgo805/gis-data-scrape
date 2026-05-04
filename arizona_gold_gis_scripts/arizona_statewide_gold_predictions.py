#!/usr/bin/env python3
"""Predict and rank statewide Arizona gold target locations from MRDS."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from arizona_common import (
    circle,
    commodities,
    comments,
    extract_years,
    first_dict,
    flatten,
    gold_importance,
    make_kmz,
    mrds_geometry,
    mrds_properties,
    snippet,
    underground_status,
    workings_summary,
    write_geojson,
)

BUILD_DATE = "2026-05-03"


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    x = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 111.32
    return (x * x + y * y) ** 0.5


def base_score(feature: dict) -> dict | None:
    props = mrds_properties(feature)
    location = first_dict(props.get("location"))
    geometry = mrds_geometry(feature)
    if location.get("state_prov") != "Arizona" or not geometry:
        return None
    importance = gold_importance(props)
    if not importance and " AU " not in (feature.get("properties", {}).get("code_list") or ""):
        return None
    deposit = props.get("deposits") if isinstance(props.get("deposits"), dict) else {}
    development = feature.get("properties", {}).get("dev_stat") or deposit.get("dev_st") or ""
    production_years = extract_years(props.get("production"), ["yr", "yr_ba"])
    ownership_years = extract_years(props.get("ownership"), ["beg_yr", "end_yr", "info_yr"])
    text = " ".join(flatten(props)).lower()
    score = 0
    reasons = []
    if importance == "Primary":
        score += 32
        reasons.append("gold is primary commodity")
    elif importance == "Secondary":
        score += 22
        reasons.append("gold is secondary commodity")
    elif importance == "Tertiary":
        score += 12
        reasons.append("gold is tertiary commodity")
    else:
        score += 10
        reasons.append("AU code present")
    if development == "Producer":
        score += 28
        reasons.append("MRDS producer")
    elif development == "Past Producer":
        score += 25
        reasons.append("MRDS past producer")
    elif development == "Prospect":
        score += 12
        reasons.append("MRDS prospect")
    elif development == "Occurrence":
        score += 7
        reasons.append("MRDS occurrence")
    status = underground_status(props, deposit)
    if status.startswith("YES"):
        score += 14
        reasons.append("underground/shaft/tunnel evidence")
    if production_years:
        score += 10
        reasons.append("production year data present")
    if any(1942 <= year <= 1945 for year in production_years + ownership_years):
        score += 5
        reasons.append("WWII-window operation/ownership evidence")
    if re.search(r"placer|alluvial|gravel|wash|gulch|creek", text):
        score += 8
        reasons.append("placer/alluvial terms")
    if re.search(r"vein|quartz|shear|fault|lode|breccia", text):
        score += 8
        reasons.append("lode/vein/structure terms")
    land_status = first_dict(props.get("land_status")).get("land_st") or ""
    if re.search(r"private|patent", land_status, re.I):
        score -= 12
        reasons.append("private/patent land-status caution")
    names = [item.get("name") for item in (props.get("name") if isinstance(props.get("name"), list) else [props.get("name")]) if isinstance(item, dict) and item.get("name")]
    name = names[0] if names else feature.get("properties", {}).get("site_name")
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "name": name,
            "mrds_dep_id": feature.get("properties", {}).get("dep_id"),
            "mrds_url": feature.get("properties", {}).get("url"),
            "county": location.get("county"),
            "district": first_dict(props.get("districts")).get("district"),
            "dev_status": development,
            "gold_importance": importance or "AU code present",
            "commodity_codes": (feature.get("properties", {}).get("code_list") or "").strip(),
            "commodities": "; ".join(f"{item['code']} {item.get('commodity') or ''} ({item.get('importance') or 'unknown'})" for item in commodities(props)),
            "operation_type": deposit.get("oper_tp"),
            "deposit_type": deposit.get("dep_tp"),
            "underground_workings_screen": status,
            "prediction_score_base": score,
            "prediction_basis_base": "; ".join(reasons),
            "production_years": ", ".join(map(str, sorted(set(production_years)))),
            "ownership_info_years": ", ".join(map(str, sorted(set(ownership_years)))),
            "land_status_mrds": land_status,
            "workings": snippet(workings_summary(props), 500),
            "notes": snippet(comments(props), 700),
            "prediction_caution": "Statewide predictive screening only; not proof of gold or claimability.",
        },
    }


def add_density_scores(records: list[dict]) -> None:
    cell_size = 0.08
    grid = defaultdict(list)
    for index, feature in enumerate(records):
        lon, lat = feature["geometry"]["coordinates"][:2]
        grid[(int(lon / cell_size), int(lat / cell_size))].append(index)
    for index, feature in enumerate(records):
        lon, lat = feature["geometry"]["coordinates"][:2]
        cx, cy = int(lon / cell_size), int(lat / cell_size)
        nearby = 0
        producers = 0
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for other_index in grid.get((cx + dx, cy + dy), []):
                    if other_index == index:
                        continue
                    other = records[other_index]
                    if distance_km((lon, lat), other["geometry"]["coordinates"][:2]) <= 5:
                        nearby += 1
                        if other["properties"].get("dev_status") in ["Producer", "Past Producer"]:
                            producers += 1
        bonus = min(20, nearby * 1.2 + producers * 1.5)
        props = feature["properties"]
        props["nearby_gold_records_5km"] = nearby
        props["nearby_producer_records_5km"] = producers
        props["density_bonus"] = round(bonus, 1)
        props["prediction_score"] = round(props.pop("prediction_score_base") + bonus, 1)
        props["prediction_basis"] = props.pop("prediction_basis_base") + (f"; {nearby} nearby gold records within 5km" if nearby else "; isolated gold record")
        score = props["prediction_score"]
        props["prediction_tier"] = "HIGH" if score >= 95 else ("MEDIUM" if score >= 70 else "LOW")


def make_cluster_zones(records: list[dict]) -> list[dict]:
    bins = defaultdict(list)
    cell = 0.1
    for feature in records:
        lon, lat = feature["geometry"]["coordinates"][:2]
        bins[(math.floor(lon / cell), math.floor(lat / cell))].append(feature)
    clusters = []
    for (cx, cy), features in bins.items():
        if len(features) < 3:
            continue
        avg = sum(item["properties"]["prediction_score"] for item in features) / len(features)
        producers = sum(1 for item in features if item["properties"].get("dev_status") in ["Producer", "Past Producer"])
        score = avg + min(25, len(features) * 2) + producers * 2
        if score < 55:
            continue
        xmin, ymin = cx * cell, cy * cell
        xmax, ymax = xmin + cell, ymin + cell
        clusters.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]]},
                "properties": {
                    "cluster_score": round(score, 1),
                    "avg_point_score": round(avg, 1),
                    "gold_record_count": len(features),
                    "producer_past_producer_count": producers,
                    "top_names": "; ".join(item["properties"]["name"] for item in sorted(features, key=lambda item: item["properties"]["prediction_score"], reverse=True)[:8]),
                    "prediction_tier": "HIGH" if score >= 95 else ("MEDIUM" if score >= 70 else "LOW"),
                    "prediction_caution": "Cluster screening only; verify claims, land status, geology, access, and safety.",
                },
            }
        )
    clusters.sort(key=lambda item: item["properties"]["cluster_score"], reverse=True)
    for rank, cluster in enumerate(clusters, 1):
        cluster["properties"]["cluster_rank"] = rank
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-mrds", required=True)
    parser.add_argument("--out", default="az_statewide_gold_predictions")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.raw_mrds).read_text(encoding="utf-8"))
    records = [item for item in (base_score(feature) for feature in raw["features"]) if item]
    add_density_scores(records)
    records.sort(key=lambda item: item["properties"]["prediction_score"], reverse=True)
    for rank, feature in enumerate(records, 1):
        feature["properties"]["rank_statewide"] = rank
    top = records[:750]
    zones = [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [circle(*feature["geometry"]["coordinates"][:2], 1609)]}, "properties": dict(feature["properties"])}
        for feature in records[:300]
    ]
    clusters = make_cluster_zones(records)
    write_geojson(out_dir / "az_statewide_gold_prediction_all_mrds_gold_points.geojson", records, "az_statewide_gold_prediction_all_mrds_gold_points", BUILD_DATE)
    write_geojson(out_dir / "az_statewide_gold_prediction_top750_points.geojson", top, "az_statewide_gold_prediction_top750_points", BUILD_DATE)
    write_geojson(out_dir / "az_statewide_gold_prediction_top300_zones.geojson", zones, "az_statewide_gold_prediction_top300_zones", BUILD_DATE)
    write_geojson(out_dir / "az_statewide_gold_prediction_cluster_zones.geojson", clusters, "az_statewide_gold_prediction_cluster_zones", BUILD_DATE)
    fields = ["rank_statewide", "name", "county", "district", "mrds_dep_id", "mrds_url", "prediction_score", "prediction_tier", "prediction_basis", "dev_status", "gold_importance", "operation_type", "underground_workings_screen", "nearby_gold_records_5km", "land_status_mrds", "prediction_caution"]
    with (out_dir / "az_statewide_gold_prediction_ranked_top1000.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for feature in records[:1000]:
            writer.writerow({field: feature["properties"].get(field, "") for field in fields})
    kml = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Arizona statewide gold prediction</name>'
    for feature in top:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"][:2]
        rows = "".join(f"<tr><th>{key}</th><td>{props.get(key, '')}</td></tr>" for key in fields)
        kml += f"<Placemark><name>{props.get('rank_statewide')}. {props.get('name')}</name><description><![CDATA[<table>{rows}</table>]]></description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
    kml += "</Document></kml>"
    kml_path = out_dir / "az_statewide_gold_predictions.kml"
    kml_path.write_text(kml, encoding="utf-8")
    make_kmz(kml_path, out_dir / "az_statewide_gold_predictions.kmz")
    summary = {
        "generated": BUILD_DATE,
        "all_gold_records": len(records),
        "top_points_exported": len(top),
        "top_zone_count": len(zones),
        "cluster_zone_count": len(clusters),
        "tier_counts_all": dict(Counter(feature["properties"]["prediction_tier"] for feature in records)),
        "caution": "Predictive screening only; not proof of gold, claimability, access, or safety.",
    }
    (out_dir / "build_summary_statewide_gold_predictions.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
