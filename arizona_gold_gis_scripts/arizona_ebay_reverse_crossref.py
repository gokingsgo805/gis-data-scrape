#!/usr/bin/env python3
"""Reverse cross-reference eBay-visible Arizona mineral listings to MRDS targets.

This is a screening tool. It does not scrape eBay directly; direct scripted
eBay reads may be blocked. Instead it uses observed, search-visible listing
evidence and maps mine/locality names backwards into an existing collector
mineral target GeoJSON.
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
    source_ref: str


EBAY_EVIDENCE: list[EbayEvidence] = [
    EbayEvidence(
        "Morenci Mine",
        "Chrysocolla",
        "CHRYSOCOLLA GEMMY Crystal Mineral Specimen Morenci Mine ARIZONA Copper Ore",
        "https://www.ebay.com/itm/396675771998",
        "US $10.39 sold / similar listings visible",
        "web search result",
    ),
    EbayEvidence(
        "79 Mine",
        "Wulfenite; Mimetite; Hemimorphite",
        "Wulfenite Crystal Mineral Specimen 79 Mine Arizona",
        "https://www.ebay.com/itm/226665604883",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "79 Mine",
        "Mimetite",
        "Mimetite 79 Mine Gila County Arizona Mineral Specimen",
        "https://www.ebay.com/itm/266927160650",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Purple Passion Mine",
        "Willemite; Fluorite; Calcite",
        "Willemite with Fluorite and Calcite, Purple Passion Mine, Wickenburg, Arizona",
        "https://www.ebay.com/itm/236298821084",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Rowley Mine",
        "Wulfenite",
        "Wulfenite Crystals Rowley Mine Arizona",
        "https://www.ebay.com/itm/336031175857",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Rowley Mine",
        "Mimetite",
        "Mimetite Rowley Mine Arizona Mineral Specimen",
        "https://www.ebay.com/itm/126133453351",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Toughnut Mine",
        "Wulfenite",
        "Wulfenite Toughnut Mine Tombstone District Arizona",
        "https://www.ebay.com/itm/117093426753",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Red Cloud Mine",
        "Wulfenite",
        "Red Cloud Mine Arizona Wulfenite Crystal Mineral Specimen",
        "https://www.ebay.com/itm/126397538799",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Red Cloud Mine",
        "Fluorite",
        "Red Cloud Mine Arizona Fluorite Mineral Specimen",
        "https://www.ebay.com/itm/256959769995",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "North Geronimo Mine",
        "Wulfenite",
        "Wulfenite North Geronimo Mine Arizona Mineral Specimen",
        "https://www.ebay.com/itm/373085721686",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Ray Mine",
        "Turquoise; Chrysocolla",
        "Ray Mine Arizona Turquoise Chrysocolla Specimen",
        "https://www.ebay.com/itm/386007846775",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Kingman Mine",
        "Turquoise",
        "Kingman Mine Turquoise Arizona marketplace category",
        "https://www.ebay.com/b/kingman-mine-turquoise/bn_7024755132",
        "category results visible",
        "web search result",
    ),
    EbayEvidence(
        "Copper Queen Mine",
        "Malachite; Quartz; Azurite",
        "Copper Queen Mine Arizona specimen listings",
        "https://www.ebay.com/str/galleryofgemsandminerals",
        "seller/store result visible",
        "web search result",
    ),
    EbayEvidence(
        "Weldon Mine",
        "Barite",
        "Weldon Mine Arizona Barite specimen listings",
        "https://www.ebay.com/str/sandskullstudio",
        "seller/store result visible",
        "web search result",
    ),
    EbayEvidence(
        "Magma Mine",
        "Baryte; Calcite",
        "Baryte Calcite Magma Mine Arizona specimen",
        "https://www.ebay.com/itm/267437256684",
        "listing visible",
        "web search result",
    ),
    EbayEvidence(
        "Planet Mine",
        "Chrysocolla",
        "Planet Mine Arizona Chrysocolla specimen results",
        "https://www.ebay.com/shop/arizona-rock-and-mineral?_nkw=arizona+rock+and+mineral",
        "shop search visible",
        "web search result",
    ),
    EbayEvidence(
        "Deer Creek",
        "Fire Agate",
        "Deer Creek Arizona Fire Agate specimen results",
        "https://www.ebay.com/shop/deer-creek-fire-agate?_nkw=deer+creek+fire+agate",
        "shop search visible",
        "web search result",
    ),
]


FIELDNAMES = [
    "mine",
    "mineral",
    "title",
    "url",
    "price",
    "source_ref",
    "match_rank",
    "match_score",
    "mineral_overlap",
    "matched_mrds_name",
    "matched_mrds_dep_id",
    "matched_county",
    "matched_target_minerals",
    "collector_score",
    "collector_tier",
    "mrds_url",
    "match_status",
]


def normalize_name(value: str) -> str:
    text = value.lower()
    text = re.sub(r"\b(the|mine|claim|claims|prospect|shaft|pit|quarry)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def mineral_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 2}


def load_features(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("features", [])


def feature_name(props: dict[str, Any]) -> str:
    return str(
        props.get("site_name")
        or props.get("name")
        or props.get("dep_name")
        or props.get("matched_mrds_name")
        or ""
    )


def feature_minerals(props: dict[str, Any]) -> str:
    values = [
        props.get("target_minerals"),
        props.get("collector_minerals"),
        props.get("commodities"),
        props.get("commod1"),
        props.get("commod2"),
        props.get("commod3"),
    ]
    return ", ".join(str(v) for v in values if v)


def score_match(evidence: EbayEvidence, props: dict[str, Any]) -> tuple[float, bool]:
    q = normalize_name(evidence.mine)
    name = normalize_name(feature_name(props))
    if not q or not name:
        return 0.0, False
    ratio = SequenceMatcher(None, q, name).ratio() * 100
    substring_bonus = 22 if q in name or name in q else 0
    mineral_overlap = bool(mineral_tokens(evidence.mineral) & mineral_tokens(feature_minerals(props)))
    mineral_bonus = 12 if mineral_overlap else 0
    return round(ratio + substring_bonus + mineral_bonus, 1), mineral_overlap


def match_status(score: float) -> str:
    if score >= 78:
        return "MATCHED_MRDS_TARGET"
    if score >= 58:
        return "POSSIBLE_MATCH_REVIEW"
    return "NO_MRDS_MATCH_FOUND"


def build_rows(features: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evidence in EBAY_EVIDENCE:
        scored: list[tuple[float, bool, dict[str, Any]]] = []
        for feature in features:
            score, overlap = score_match(evidence, feature.get("properties", {}))
            if score >= 58:
                scored.append((score, overlap, feature))
        scored.sort(key=lambda item: item[0], reverse=True)

        for rank, (score, overlap, feature) in enumerate(scored[:limit], start=1):
            props = feature.get("properties", {})
            dep_id = props.get("dep_id") or props.get("mrds_dep_id") or props.get("id")
            rows.append(
                {
                    "mine": evidence.mine,
                    "mineral": evidence.mineral,
                    "title": evidence.title,
                    "url": evidence.url,
                    "price": evidence.price,
                    "source_ref": evidence.source_ref,
                    "match_rank": rank,
                    "match_score": score,
                    "mineral_overlap": overlap,
                    "matched_mrds_name": feature_name(props),
                    "matched_mrds_dep_id": dep_id,
                    "matched_county": props.get("county") or props.get("county_name") or "",
                    "matched_target_minerals": feature_minerals(props),
                    "collector_score": props.get("collector_score", ""),
                    "collector_tier": props.get("collector_tier", ""),
                    "mrds_url": f"https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id={dep_id}" if dep_id else "",
                    "match_status": match_status(score),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(path: Path, rows: list[dict[str, Any]], features: list[dict[str, Any]]) -> None:
    by_dep = {
        str((f.get("properties") or {}).get("dep_id") or (f.get("properties") or {}).get("mrds_dep_id")): f
        for f in features
    }
    out_features = []
    for row in rows:
        source = by_dep.get(str(row["matched_mrds_dep_id"]))
        if not source:
            continue
        out_features.append(
            {
                "type": "Feature",
                "geometry": source.get("geometry"),
                "properties": row,
            }
        )
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": out_features}, indent=2),
        encoding="utf-8",
    )


def coords_from_geometry(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    if not geometry or geometry.get("type") != "Point":
        return None
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None
    return float(coords[0]), float(coords[1])


def write_kmz(kmz_path: Path, rows: list[dict[str, Any]], features: list[dict[str, Any]]) -> None:
    by_dep = {
        str((f.get("properties") or {}).get("dep_id") or (f.get("properties") or {}).get("mrds_dep_id")): f
        for f in features
    }
    placemarks = []
    for row in rows:
        source = by_dep.get(str(row["matched_mrds_dep_id"]))
        point = coords_from_geometry(source.get("geometry") if source else None)
        if not point:
            continue
        lon, lat = point
        description = "<br/>".join(
            f"<b>{escape(k)}</b>: {escape(str(row.get(k, '')))}" for k in FIELDNAMES
        )
        placemarks.append(
            f"<Placemark><name>{escape(str(row['mine']))}: "
            f"{escape(str(row['mineral']))}</name><description>{description}</description>"
            f"<Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
        )
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<name>Arizona eBay reverse mine mineral cross-reference</name>"
        + "".join(placemarks)
        + "</Document></kml>"
    )
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)


def update_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        summary = json.loads(path.read_text(encoding="utf-8"))
    else:
        summary = {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    summary.update(
        {
            "ebay_reverse_crossref_listing_count": len(EBAY_EVIDENCE),
            "ebay_reverse_crossref_rows": len(rows),
            "ebay_reverse_crossref_status_counts": counts,
            "ebay_reverse_crossref_note": (
                "Reverse cross-reference uses observed search-visible eBay results "
                "and direct eBay URLs; it is not a complete eBay scrape."
            ),
        }
    )
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def refresh_package(zip_path: Path, output_dir: Path) -> None:
    files = [
        "az_ebay_reverse_mine_mineral_crossref.csv",
        "az_ebay_reverse_mine_mineral_crossref.geojson",
        "az_ebay_reverse_mine_mineral_crossref.kmz",
        "build_summary_collector_mineral_targets.json",
    ]
    existing: dict[str, bytes] = {}
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            existing = {name: z.read(name) for name in z.namelist() if name not in files}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in existing.items():
            z.writestr(name, data)
        for name in files:
            p = output_dir / name
            if p.exists():
                z.write(p, arcname=name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collector-geojson",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "az_collector_mineral_targets_all.geojson",
    )
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
