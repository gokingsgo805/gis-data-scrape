#!/usr/bin/env python3
"""Build Arizona MRDS gold and WWII-window past-producer layers."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from arizona_common import (
    MRDS_ITEMS_URL,
    as_list,
    commodities,
    comments,
    extract_years,
    first_dict,
    gold_importance,
    make_kmz,
    mrds_geometry,
    mrds_properties,
    query_url,
    request_json,
    snippet,
    underground_status,
    workings_summary,
    write_geojson,
)

BUILD_DATE = "2026-05-03"
AZ_BBOX = "-115.1,31.2,-109.0,37.1"


def fetch_arizona_mrds(out_dir: Path) -> list[dict]:
    features = []
    for offset in range(0, 40000, 10000):
        params = {"f": "json", "limit": "10000", "offset": str(offset), "bbox": AZ_BBOX}
        data = request_json(query_url(MRDS_ITEMS_URL, params), timeout=240)
        batch = data.get("features", [])
        features.extend(batch)
        if len(batch) < 10000:
            break
    raw = {"type": "FeatureCollection", "source": MRDS_ITEMS_URL, "features": features}
    (out_dir / "mrds_arizona_raw.geojson").write_text(json.dumps(raw), encoding="utf-8")
    return features


def gold_records(features: list[dict]) -> list[dict]:
    records = []
    for feature in features:
        props = mrds_properties(feature)
        location = first_dict(props.get("location"))
        geometry = mrds_geometry(feature)
        if location.get("state_prov") != "Arizona" or not geometry:
            continue
        importance = gold_importance(props)
        if not importance and " AU " not in (feature.get("properties", {}).get("code_list") or ""):
            continue
        deposit = props.get("deposits") if isinstance(props.get("deposits"), dict) else {}
        production_years = extract_years(props.get("production"), ["yr", "yr_ba"])
        ownership_years = extract_years(props.get("ownership"), ["beg_yr", "end_yr", "info_yr"])
        name = feature.get("properties", {}).get("site_name")
        names = [item.get("name") for item in as_list(props.get("name")) if isinstance(item, dict) and item.get("name")]
        if names:
            name = names[0]
        records.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "name": name,
                    "county": location.get("county"),
                    "district": first_dict(props.get("districts")).get("district"),
                    "mrds_dep_id": feature.get("properties", {}).get("dep_id"),
                    "mrds_url": feature.get("properties", {}).get("url"),
                    "dev_status": feature.get("properties", {}).get("dev_stat") or deposit.get("dev_st"),
                    "gold_importance": importance or "AU code present",
                    "commodity_codes": (feature.get("properties", {}).get("code_list") or "").strip(),
                    "commodities": "; ".join(
                        f"{item['code']} {item.get('commodity') or ''} ({item.get('importance') or 'unknown'})"
                        for item in commodities(props)
                    ),
                    "operation_type": deposit.get("oper_tp"),
                    "deposit_type": deposit.get("dep_tp"),
                    "underground_workings_screen": underground_status(props, deposit),
                    "production_years": ", ".join(map(str, sorted(set(production_years)))),
                    "ownership_info_years": ", ".join(map(str, sorted(set(ownership_years)))),
                    "ww2_window_years": ", ".join(
                        map(str, sorted({y for y in production_years + ownership_years if 1942 <= y <= 1945}))
                    ),
                    "land_status_mrds": first_dict(props.get("land_status")).get("land_st"),
                    "workings": snippet(workings_summary(props), 500),
                    "notes": snippet(comments(props), 700),
                    "source": "USGS MRDS",
                    "legal_caution": "Screening only; not legal claimability, access, ownership, patent, withdrawal, or safety determination.",
                },
            }
        )
    return records


def ww2_past_producers(records: list[dict]) -> list[dict]:
    selected = []
    for record in records:
        props = record["properties"]
        if props.get("dev_status") != "Past Producer":
            continue
        years = []
        for field in ["production_years", "ownership_info_years"]:
            years.extend(int(y) for y in props.get(field, "").replace(",", " ").split() if y.isdigit())
        ww2 = sorted({y for y in years if 1942 <= y <= 1945})
        postwar = sorted({y for y in years if 1946 <= y <= 1999})
        if ww2 and not postwar:
            new_record = json.loads(json.dumps(record))
            new_record["properties"]["screening_result"] = (
                "Included: MRDS Past Producer gold site with 1942-1945 production/ownership year "
                "and no parsed post-1945 operation year."
            )
            selected.append(new_record)
    return selected


def write_csv(path: Path, features: list[dict]) -> None:
    fields = [
        "name",
        "county",
        "district",
        "mrds_dep_id",
        "mrds_url",
        "dev_status",
        "gold_importance",
        "operation_type",
        "underground_workings_screen",
        "ww2_window_years",
        "land_status_mrds",
        "legal_caution",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for feature in features:
            writer.writerow({field: feature["properties"].get(field, "") for field in fields})


def write_kmz(out_dir: Path, features: list[dict]) -> None:
    placemarks = []
    for feature in features:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"][:2]
        rows = "".join(f"<tr><th>{key}</th><td>{props.get(key, '')}</td></tr>" for key in props)
        placemarks.append(
            f"<Placemark><name>{props.get('name')}</name><description><![CDATA[<table>{rows}</table>]]></description>"
            f"<Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
        )
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<name>Arizona WWII-window past-producer gold mines</name>"
        + "".join(placemarks)
        + "</Document></kml>"
    )
    kml_path = out_dir / "az_ww2_shutdown_never_reopened_gold_mines.kml"
    kml_path.write_text(kml, encoding="utf-8")
    make_kmz(kml_path, out_dir / "az_ww2_shutdown_never_reopened_gold_mines.kmz")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="az_gold_outputs")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    features = fetch_arizona_mrds(out_dir)
    all_gold = gold_records(features)
    ww2 = ww2_past_producers(all_gold)
    write_geojson(out_dir / "az_all_mrds_gold_records.geojson", all_gold, "az_all_mrds_gold_records", BUILD_DATE)
    write_geojson(
        out_dir / "az_ww2_shutdown_never_reopened_gold_mines_all_screened.geojson",
        ww2,
        "az_ww2_shutdown_never_reopened_gold_mines_all_screened",
        BUILD_DATE,
    )
    write_csv(out_dir / "az_ww2_shutdown_never_reopened_gold_mines_all_screened.csv", ww2)
    write_kmz(out_dir, ww2)
    summary = {"generated": BUILD_DATE, "raw_mrds_features": len(features), "gold_records": len(all_gold), "ww2_screened": len(ww2)}
    (out_dir / "build_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
