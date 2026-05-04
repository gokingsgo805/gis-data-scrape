#!/usr/bin/env python3
"""Reverse cross-reference eBay-visible Arizona mineral listings to MRDS targets.

This screening script takes observed eBay listing evidence, matches mine/locality
names backwards into an existing Arizona collector mineral MRDS GeoJSON, and
writes CSV, GeoJSON, and KMZ layers.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

DEFAULT_OUTPUT_DIR = Path(
    "/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/"
    "az_collector_mineral_targets_2026-05-03"
)


@dataclass(frozen=True)
class EbayEvidence:
    mine: str
    mineral: str
    title: str
    url: str
    price: str
    source_ref: str = "web-search-visible eBay result"


EBAY_EVIDENCE = [
    EbayEvidence("Morenci Mine", "Chrysocolla", "CHRYSOCOLLA GEMMY Crystal Mineral Specimen Morenci Mine ARIZONA Copper Ore", "https://www.ebay.com/itm/396675771998", "US $10.39 sold / similar listings visible"),
    EbayEvidence("79 Mine", "Wulfenite; Mimetite; Hemimorphite", "Wulfenite Crystal Mineral Specimen 79 Mine Arizona", "https://www.ebay.com/itm/226665604883", "listing visible"),
    EbayEvidence("79 Mine", "Mimetite", "Mimetite 79 Mine Gila County Arizona Mineral Specimen", "https://www.ebay.com/itm/266927160650", "listing visible"),
    EbayEvidence("Purple Passion Mine", "Willemite; Fluorite; Calcite", "Willemite with Fluorite and Calcite, Purple Passion Mine, Wickenburg, Arizona", "https://www.ebay.com/itm/236298821084", "listing visible"),
    EbayEvidence("Rowley Mine", "Wulfenite", "Wulfenite Crystals Rowley Mine Arizona", "https://www.ebay.com/itm/336031175857", "listing visible"),
    EbayEvidence("Rowley Mine", "Mimetite", "Mimetite Rowley Mine Arizona Mineral Specimen", "https://www.ebay.com/itm/126133453351", "listing visible"),
    EbayEvidence("Toughnut Mine", "Wulfenite", "Wulfenite Toughnut Mine Tombstone District Arizona", "https://www.ebay.com/itm/117093426753", "listing visible"),
    EbayEvidence("Red Cloud Mine", "Wulfenite", "Red Cloud Mine Arizona Wulfenite Crystal Mineral Specimen", "https://www.ebay.com/itm/126397538799", "listing visible"),
    EbayEvidence("Red Cloud Mine", "Fluorite", "Red Cloud Mine Arizona Fluorite Mineral Specimen", "https://www.ebay.com/itm/256959769995", "listing visible"),
    EbayEvidence("North Geronimo Mine", "Wulfenite", "Wulfenite North Geronimo Mine Arizona Mineral Specimen", "https://www.ebay.com/itm/373085721686", "listing visible"),
    EbayEvidence("Ray Mine", "Turquoise; Chrysocolla", "Ray Mine Arizona Turquoise Chrysocolla Specimen", "https://www.ebay.com/itm/386007846775", "listing visible"),
    EbayEvidence("Kingman Mine", "Turquoise", "Kingman Mine Turquoise Arizona marketplace category", "https://www.ebay.com/b/kingman-mine-turquoise/bn_7024755132", "category results visible"),
    EbayEvidence("Copper Queen Mine", "Malachite; Quartz; Azurite", "Copper Queen Mine Arizona specimen listings", "https://www.ebay.com/str/galleryofgemsandminerals", "seller/store result visible"),
    EbayEvidence("Weldon Mine", "Barite", "Weldon Mine Arizona Barite specimen listings", "https://www.ebay.com/str/sandskullstudio", "seller/store result visible"),
    EbayEvidence("Magma Mine", "Baryte; Calcite", "Baryte Calcite Magma Mine Arizona specimen", "https://www.ebay.com/itm/267437256684", "listing visible"),
    EbayEvidence("Planet Mine", "Chrysocolla", "Planet Mine Arizona Chrysocolla specimen results", "https://www.ebay.com/shop/arizona-rock-and-mineral?_nkw=arizona+rock+and+mineral", "shop search visible"),
    EbayEvidence("Deer Creek", "Fire Agate", "Deer Creek Arizona Fire Agate specimen results", "https://www.ebay.com/shop/deer-creek-fire-agate?_nkw=deer+creek+fire+agate", "shop search visible"),
]

FIELDNAMES = [
    "mine", "mineral", "title", "url", "price", "source_ref", "match_rank",
    "match_score", "mineral_overlap", "matched_mrds_name", "matched_mrds_dep_id",
    "matched_county", "matched_target_minerals", "collector_score", "collector_tier",
    "mrds_url", "match_status",
]


def normalize_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b(the|mine|claim|claims|prospect|shaft|pit|quarry)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def mineral_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 2}


def load_features(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")).get("features", [])


def props(feature: dict[str, Any]) -> dict[str, Any]:
    return feature.get("properties") or {}


def feature_name(p: dict[str, Any]) -> str:
    return str(p.get("site_name") or p.get("name") or p.get("dep_name") or "")


def feature_minerals(p: dict[str, Any]) -> str:
    keys = ["target_minerals", "collector_minerals", "commodities", "commod1", "commod2", "commod3"]
    return ", ".join(str(p.get(k)) for k in keys if p.get(k))


def score_match(evidence: EbayEvidence, p: dict[str, Any]) -> tuple[float, bool]:
    query = normalize_name(evidence.mine)
    candidate = normalize_name(feature_name(p))
    if not query or not candidate:
        return 0.0, False
    ratio = SequenceMatcher(None, query, candidate).ratio() * 100
    name_bonus = 22 if query in candidate or candidate in query else 0
    overlap = bool(mineral_tokens(evidence.mineral) & mineral_tokens(feature_minerals(p)))
    mineral_bonus = 12 if overlap else 0
    return round(ratio + name_bonus + mineral_bonus, 1), overlap


def status(score: float) -> str:
    if score >= 78:
        return "MATCHED_MRDS_TARGET"
    if score >= 58:
        return "POSSIBLE_MATCH_REVIEW"
    return "NO_MRDS_MATCH_FOUND"


def dep_id(p: dict[str, Any]) -> str:
    return str(p.get("dep_id") or p.get("mrds_dep_id") or p.get("id") or "")


def build_rows(features: list[dict[str, Any]], matches_per_listing: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evidence in EBAY_EVIDENCE:
        matches = []
        for feature in features:
            p = props(feature)
            score, overlap = score_match(evidence, p)
            if score >= 58:
                matches.append((score, overlap, feature))
        matches.sort(key=lambda item: item[0], reverse=True)
        for rank, (score, overlap, feature) in enumerate(matches[:matches_per_listing], start=1):
            p = props(feature)
            did = dep_id(p)
            rows.append({
                "mine": evidence.mine,
                "mineral": evidence.mineral,
                "title": evidence.title,
                "url": evidence.url,
                "price": evidence.price,
                "source_ref": evidence.source_ref,
                "match_rank": rank,
                "match_score": score,
                "mineral_overlap": overlap,
                "matched_mrds_name": feature_name(p),
                "matched_mrds_dep_id": did,
                "matched_county": p.get("county") or p.get("county_name") or "",
                "matched_target_minerals": feature_minerals(p),
                "collector_score": p.get("collector_score", ""),
                "collector_tier": p.get("collector_tier", ""),
                "mrds_url": f"https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id={did}" if did else "",
                "match_status": status(score),
            })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def feature_index(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {dep_id(props(feature)): feature for feature in features if dep_id(props(feature))}


def write_geojson(path: Path, rows: list[dict[str, Any]], features: list[dict[str, Any]]) -> None:
    by_dep = feature_index(features)
    out = []
    for row in rows:
        source = by_dep.get(str(row["matched_mrds_dep_id"]))
        if source:
            out.append({"type": "Feature", "geometry": source.get("geometry"), "properties": row})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": out}, indent=2), encoding="utf-8")


def point(feature: dict[str, Any] | None) -> tuple[float, float] | None:
    if not feature:
        return None
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point" or len(geom.get("coordinates") or []) < 2:
        return None
    lon, lat = geom["coordinates"][:2]
    return float(lon), float(lat)


def write_kmz(path: Path, rows: list[dict[str, Any]], features: list[dict[str, Any]]) -> None:
    by_dep = feature_index(features)
    placemarks = []
    for row in rows:
        pt = point(by_dep.get(str(row["matched_mrds_dep_id"])))
        if not pt:
            continue
        lon, lat = pt
        desc = "<br/>".join(f"<b>{escape(k)}</b>: {escape(str(row.get(k, '')))}" for k in FIELDNAMES)
        placemarks.append(
            f"<Placemark><name>{escape(row['mine'])}: {escape(row['mineral'])}</name>"
            f"<description>{desc}</description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
        )
    kml = "".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        '<name>Arizona eBay reverse mine mineral cross-reference</name>',
        *placemarks,
        '</Document></kml>',
    ])
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml)


def update_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    summary.update({
        "ebay_reverse_crossref_listing_count": len(EBAY_EVIDENCE),
        "ebay_reverse_crossref_rows": len(rows),
        "ebay_reverse_crossref_status_counts": counts,
        "ebay_reverse_crossref_note": "Uses observed search-visible eBay results and direct URLs; not a complete eBay scrape.",
    })
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def refresh_package(zip_path: Path, output_dir: Path) -> None:
    wanted = [
        "az_ebay_reverse_mine_mineral_crossref.csv",
        "az_ebay_reverse_mine_mineral_crossref.geojson",
        "az_ebay_reverse_mine_mineral_crossref.kmz",
        "build_summary_collector_mineral_targets.json",
    ]
    existing: dict[str, bytes] = {}
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as archive:
            existing = {name: archive.read(name) for name in archive.namelist() if name not in wanted}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in existing.items():
            archive.writestr(name, data)
        for name in wanted:
            candidate = output_dir / name
            if candidate.exists():
                archive.write(candidate, arcname=name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector-geojson", type=Path, default=DEFAULT_OUTPUT_DIR / "az_collector_mineral_targets_all.geojson")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--matches-per-listing", type=int, default=5)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    features = load_features(args.collector_geojson)
    rows = build_rows(features, args.matches_per_listing)
    write_csv(args.output_dir / "az_ebay_reverse_mine_mineral_crossref.csv", rows)
    write_geojson(args.output_dir / "az_ebay_reverse_mine_mineral_crossref.geojson", rows, features)
    write_kmz(args.output_dir / "az_ebay_reverse_mine_mineral_crossref.kmz", rows, features)
    update_summary(args.output_dir / "build_summary_collector_mineral_targets.json", rows)
    refresh_package(args.output_dir / "az_collector_mineral_targets_package.zip", args.output_dir)
    print(f"listing_count={len(EBAY_EVIDENCE)}")
    print(f"rows={len(rows)}")
    print(f"output_dir={args.output_dir}")


if __name__ == "__main__":
    main()
