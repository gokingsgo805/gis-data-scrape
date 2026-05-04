#!/usr/bin/env python3
"""Build Arizona collector-mineral target layers from MRDS.

Screens for fluorite, fire agate, agate/geode/chalcedony, opal, Arizona
ruby/garnet, chrysocolla, wulfenite, turquoise, malachite/azurite,
vanadinite/mimetite, cerussite/anglesite, smithsonite, quartz/amethyst,
barite/calcite, peridot/olivine, and rhodochrosite/manganese minerals.

Adds eBay cross-reference fields:
- direct eBay search URL for every mine/mineral pair
- observed eBay evidence for notable Arizona mine/mineral pairs

Screening only. Not proof of specimens, claimability, access, land status, or
safety.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import urllib.parse
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

BUILD_DATE = "2026-05-03"

MINERALS = {
    "fluorite": ["fluorite", "fluorspar", " flourite", r"\bf\b"],
    "fire_agate": ["fire agate"],
    "agate_geode_chalcedony": ["agate", "geode", "chalcedony", "jasper"],
    "opal": ["opal"],
    "arizona_ruby_garnet": ["ruby", "garnet", "pyrope"],
    "chrysocolla": ["chrysocolla"],
    "wulfenite": ["wulfenite", "molybdate"],
    "turquoise": ["turquoise"],
    "malachite_azurite": ["malachite", "azurite"],
    "vanadinite_mimetite": ["vanadinite", "mimetite"],
    "cerussite_anglesite": ["cerussite", "anglesite"],
    "smithsonite": ["smithsonite"],
    "quartz_amethyst": ["amethyst", "quartz crystal", "rock crystal", "crystal quartz"],
    "barite_calcite": ["barite", "baryte", "calcite"],
    "peridot_olivine": ["peridot", "olivine"],
    "rhodochrosite_manganese": ["rhodochrosite", "manganese oxide", "pyrolusite", "psilomelane"],
}

HIGH_VALUE = {"wulfenite", "chrysocolla", "turquoise", "fire_agate", "opal", "arizona_ruby_garnet", "fluorite", "vanadinite_mimetite"}
COPPER_CONTEXT = ["cu", "copper", "oxide", "oxidized", "malachite", "azurite", "chrysocolla", "turquoise"]
LEAD_CONTEXT = ["pb", "lead", "wulfenite", "mimetite", "vanadinite", "cerussite", "anglesite"]
DISCARDED_TERMS = ["gangue", "dump", "dumps", "tailings", "waste", "stockpile", "old workings", "mine dump", "ore dump", "discarded", "low grade", "oxidized", "surface material"]

EBAY_EVIDENCE = [
    {"match": ["red cloud"], "minerals": ["wulfenite", "fluorite"], "evidence": "eBay-visible results show Red Cloud Mine wulfenite and fluorite specimens.", "urls": ["https://www.ebay.com/b/red-cloud-mine/bn_7024885868", "https://www.ebay.com/shop/red-cloud-mine?_nkw=red+cloud+mine"]},
    {"match": ["mammoth", "st. anthony", "st anthony"], "minerals": ["wulfenite", "chrysocolla", "fluorite"], "evidence": "eBay-visible result: Wulfenite crystals from Mammoth St. Anthony Mine, Tiger, Arizona.", "urls": ["https://www.ebay.com/sch/i.html?_nkw=Mammoth+St+Anthony+Mine+wulfenite+Arizona+specimen"]},
    {"match": ["ray mine", "old ray"], "minerals": ["turquoise", "chrysocolla"], "evidence": "eBay-visible sold listing: Old Ray Mine turquoise/chrysocolla rough specimen, Arizona.", "urls": ["https://www.ebay.com/itm/386007846775"]},
    {"match": ["morenci"], "minerals": ["turquoise", "chrysocolla"], "evidence": "eBay-visible listings show Morenci Mine chrysocolla and turquoise rough/specimen material.", "urls": ["https://www.ebay.com/itm/397174335527", "https://www.ebay.com/itm/187194017442"]},
    {"match": ["rowley"], "minerals": ["wulfenite"], "evidence": "eBay-visible listing: Wulfenite collector quality specimen from Rowley Mine, Arizona.", "urls": ["https://www.ebay.com/itm/358355721625"]},
    {"match": ["79 mine", "seventy nine"], "minerals": ["wulfenite", "vanadinite_mimetite"], "evidence": "eBay-visible listings show Arizona 79 Mine wulfenite/hemimorphite specimens.", "urls": ["https://www.ebay.com/itm/257401514910", "https://www.ebay.com/itm/366268759784"]},
    {"match": ["north geronimo", "geronimo"], "minerals": ["wulfenite"], "evidence": "eBay-visible listing: North Geronimo Mine Arizona wulfenite mineral specimen.", "urls": ["https://www.ebay.com/itm/373085721686"]},
    {"match": ["kingman"], "minerals": ["turquoise"], "evidence": "eBay-visible category/search results show Kingman Mine Arizona turquoise rough/specimens.", "urls": ["https://www.ebay.com/b/kingman-mine-turquoise/bn_7024755132"]},
    {"match": ["copper queen"], "minerals": ["malachite_azurite", "quartz_amethyst"], "evidence": "eBay-visible store result referenced Malachite & Quartz from Copper Queen Mine, Arizona.", "urls": ["https://www.ebay.com/str/galleryofgemsandminerals"]},
    {"match": ["deer creek"], "minerals": ["fire_agate"], "evidence": "eBay-visible category/search results show Deer Creek / Arizona fire agate specimens.", "urls": ["https://www.ebay.com/shop/deer-creek-fire-agate?_nkw=deer+creek+fire+agate"]},
]

GENERAL_EBAY = {
    "turquoise": ("https://www.ebay.com/shop/arizona-turquoise?_nkw=arizona+turquoise", "Arizona turquoise has a large eBay-visible market."),
    "wulfenite": ("https://www.ebay.com/b/Wulfenite/3225/bn_55194589", "Arizona wulfenite has eBay-visible mine-name specimen listings."),
    "fire_agate": ("https://www.ebay.com/shop/fire-agate-arizona?_nkw=fire+agate+arizona", "Arizona fire agate has eBay-visible rough and specimen listings."),
}


def as_list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def parsed(feature):
    try:
        return json.loads(feature.get("properties", {}).get("json") or "{}")
    except Exception:
        return {}


def props(feature):
    return parsed(feature).get("properties", {})


def geom(feature):
    return feature.get("geometry") or parsed(feature).get("geometry")


def first_dict(value):
    values = as_list(value)
    return values[0] if values and isinstance(values[0], dict) else {}


def flat(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from flat(item)
    elif isinstance(value, list):
        for item in value:
            yield from flat(item)
    elif value is not None:
        yield str(value)


def commodities(pr):
    rows = []
    for c in as_list(pr.get("commodity")):
        if isinstance(c, dict) and c.get("code"):
            rows.append({"code": c.get("code"), "commodity": c.get("commod"), "importance": c.get("import")})
    return rows


def years(values, keys):
    out = []
    for item in as_list(values):
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value and re.fullmatch(r"\d{4}", str(value)):
                    out.append(int(value))
    return out


def snippet(parts, limit=900):
    return re.sub(r"\s+", " ", " | ".join(part for part in parts if part)).strip()[:limit]


def text_parts(pr):
    rows = []
    for key in ["material", "commodity", "orebody", "analytical_data", "comment", "rock", "alteration", "production"]:
        for item in as_list(pr.get(key)):
            if isinstance(item, dict):
                rows.extend(str(v) for v in item.values() if v)
    return rows


def workings(pr):
    rows = []
    for w in as_list(pr.get("workings")):
        if not isinstance(w, dict):
            continue
        parts = []
        for key, label in [("wrk_tp", "type"), ("depth", "depth"), ("len", "length"), ("ovr_len", "overall_length"), ("area", "area")]:
            if w.get(key):
                parts.append(f"{label}={w[key]}")
        if parts:
            rows.append("; ".join(parts))
    return rows


def underground_status(pr, deposit):
    op = (deposit.get("oper_tp") or "").lower()
    text = (" ".join(flat(pr)) + " " + " ".join(workings(pr))).lower()
    if "underground" in op or any(t in text for t in ["shaft", "adit", "tunnel", "drift", "stope"]):
        return "YES"
    if "surface" in op:
        return "NO_SURFACE_ONLY_IN_MRDS"
    return "UNKNOWN_NOT_STATED_IN_MRDS"


def match_minerals(text, codes):
    low = text.lower()
    code_text = " " + codes.lower() + " "
    found = []
    for mineral, patterns in MINERALS.items():
        for pattern in patterns:
            if pattern.startswith("\\b"):
                if re.search(pattern, code_text):
                    found.append(mineral); break
            elif pattern.strip() in low:
                found.append(mineral); break
    if any(t in low or f" {t} " in code_text for t in COPPER_CONTEXT) and re.search(r"oxid|carbonate|silicate|secondary|supergene|gossan", low):
        found += ["chrysocolla_context", "malachite_azurite_context"]
    if any(t in low or f" {t} " in code_text for t in LEAD_CONTEXT) and re.search(r"oxid|carbonate|secondary|supergene|limestone|replacement", low):
        found.append("wulfenite_context")
    return sorted(set(found))


def top_mineral(targets):
    vals = [v for v in targets.split(", ") if v]
    priority = ["wulfenite", "chrysocolla", "turquoise", "fire_agate", "opal", "fluorite", "vanadinite_mimetite", "malachite_azurite", "agate_geode_chalcedony", "arizona_ruby_garnet"]
    for item in priority:
        if item in vals:
            return item
    return vals[0] if vals else "Arizona mineral specimen"


def ebay_search_url(query):
    return "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode({"_nkw": query})


def add_ebay_fields(properties):
    mine = (properties.get("name") or "").lower()
    targets = properties.get("target_minerals", "")
    top = top_mineral(targets)
    query = f"{properties.get('name')} {top.replace('_', ' ')} Arizona mineral specimen"
    properties["ebay_search_query"] = query
    properties["ebay_search_url"] = ebay_search_url(query)
    properties["ebay_crossref_status"] = "SEARCH_URL_ONLY_NOT_VERIFIED"
    properties["ebay_market_evidence"] = "Direct eBay search URL generated for mine/mineral pair; no specific listing evidence attached."
    properties["ebay_example_urls"] = ""
    for evidence in EBAY_EVIDENCE:
        if any(match in mine for match in evidence["match"]) and any(mineral in targets for mineral in evidence["minerals"]):
            properties["ebay_crossref_status"] = "OBSERVED_EBAY_RESULTS"
            properties["ebay_market_evidence"] = evidence["evidence"]
            properties["ebay_example_urls"] = "; ".join(evidence["urls"])
            properties["collector_score"] += 15
            properties["screening_basis"] += "; eBay market cross-reference observed for mine/mineral pair"
            return
    for mineral, (url, note) in GENERAL_EBAY.items():
        if mineral in targets:
            properties["ebay_market_category_url"] = url
            properties["ebay_market_category_note"] = note
            return
    properties["ebay_market_category_url"] = "https://www.ebay.com/sch/i.html?_nkw=Arizona+mineral+specimen"
    properties["ebay_market_category_note"] = "General Arizona mineral specimen search."


def build_targets(raw_features):
    records = []
    for feature in raw_features:
        pr = props(feature)
        location = first_dict(pr.get("location"))
        geometry = geom(feature)
        if location.get("state_prov") != "Arizona" or not geometry or geometry.get("type") != "Point":
            continue
        deposit = pr.get("deposits") if isinstance(pr.get("deposits"), dict) else {}
        codes = feature.get("properties", {}).get("code_list") or ""
        text = " ".join(flat(pr))
        matches = match_minerals(text, codes)
        if not matches:
            continue
        names = [n.get("name") for n in as_list(pr.get("name")) if isinstance(n, dict) and n.get("name")]
        name = names[0] if names else feature.get("properties", {}).get("site_name")
        dev = feature.get("properties", {}).get("dev_stat") or deposit.get("dev_st") or ""
        production_years = years(pr.get("production"), ["yr", "yr_ba"])
        ownership_years = years(pr.get("ownership"), ["beg_yr", "end_yr", "info_yr"])
        discarded = bool(re.search("|".join(re.escape(t) for t in DISCARDED_TERMS), text, re.I))
        direct = [m for m in matches if not m.endswith("_context")]
        context = [m for m in matches if m.endswith("_context")]
        score = len(direct) * 18 + len(context) * 8
        reasons = []
        if direct: reasons.append("direct MRDS/material/comment mineral term match: " + ", ".join(direct))
        if context: reasons.append("geologic context inference: " + ", ".join(context))
        if any(m in HIGH_VALUE for m in direct): score += 20; reasons.append("high collector-value Arizona mineral group")
        if dev == "Past Producer": score += 20; reasons.append("past producer with old workings/mineral record")
        elif dev == "Producer": score += 16; reasons.append("producer record")
        elif dev == "Prospect": score += 10; reasons.append("prospect record")
        elif dev == "Occurrence": score += 6; reasons.append("occurrence record")
        u = underground_status(pr, deposit)
        if u == "YES": score += 12; reasons.append("underground/shaft/tunnel evidence")
        if discarded: score += 18; reasons.append("dump/gangue/tailings/waste/low-grade terms suggest discarded material potential")
        if production_years or ownership_years: score += 8; reasons.append("historical production/ownership year data")
        if any(y < 1960 for y in production_years + ownership_years): score += 6; reasons.append("older operation era before modern specimen market")
        if re.search(r"oxid|supergene|gossan|carbonate|silicate", text, re.I): score += 8; reasons.append("oxidized/supergene mineral setting")
        out = {
            "name": name, "county": location.get("county"), "district": first_dict(pr.get("districts")).get("district"),
            "mrds_dep_id": feature.get("properties", {}).get("dep_id"), "mrds_url": feature.get("properties", {}).get("url"),
            "collector_score": score, "collector_tier": "HIGH" if score >= 90 else ("MEDIUM" if score >= 60 else "LOW"),
            "target_minerals": ", ".join(matches), "direct_mineral_matches": ", ".join(direct), "context_inferred_matches": ", ".join(context),
            "discarded_value_now_screen": "YES" if discarded or context else ("POSSIBLE" if dev in ["Past Producer", "Producer"] else "UNKNOWN"),
            "screening_basis": "; ".join(reasons), "dev_status": dev, "operation_type": deposit.get("oper_tp"), "deposit_type": deposit.get("dep_tp"),
            "underground_workings_screen": u, "commodity_codes": codes.strip(),
            "commodities": "; ".join(f"{c['code']} {c.get('commodity') or ''} ({c.get('importance') or 'unknown'})" for c in commodities(pr)),
            "production_years": ", ".join(map(str, sorted(set(production_years)))), "ownership_info_years": ", ".join(map(str, sorted(set(ownership_years)))),
            "land_status_mrds": first_dict(pr.get("land_status")).get("land_st"), "workings": snippet(workings(pr), 700), "evidence_text": snippet(text_parts(pr), 1200),
            "claim_status_note": "Cross-check against live BLM claim-status layers before field work or staking.",
            "legal_caution": "Screening only. Not proof of collectible material, legal claimability, access, land status, patent/private land, withdrawal, or safety.",
        }
        add_ebay_fields(out)
        records.append({"type": "Feature", "geometry": geometry, "properties": out})
    records.sort(key=lambda f: f["properties"]["collector_score"], reverse=True)
    for rank, feature in enumerate(records, 1):
        feature["properties"]["rank_collector"] = rank
        score = feature["properties"]["collector_score"]
        feature["properties"]["collector_tier"] = "HIGH" if score >= 90 else ("MEDIUM" if score >= 60 else "LOW")
    return records


def write_geojson(path, features, name):
    path.write_text(json.dumps({"type": "FeatureCollection", "name": name, "generated": BUILD_DATE, "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")


def make_kmz(kml_path, kmz_path):
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(kml_path, arcname="doc.kml")


def write_outputs(records, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    write_geojson(out_dir / "az_collector_mineral_targets_all.geojson", records, "az_collector_mineral_targets_all")
    by_theme = defaultdict(list)
    for feature in records:
        for mineral in feature["properties"].get("target_minerals", "").split(", "):
            by_theme[mineral.replace("_context", "")].append(feature)
    for theme, features in by_theme.items():
        safe = re.sub(r"[^a-z0-9_]+", "_", theme.lower())
        write_geojson(out_dir / f"az_collector_{safe}_targets.geojson", features, f"az_collector_{safe}_targets")
    fields = ["rank_collector", "name", "county", "district", "mrds_dep_id", "mrds_url", "collector_score", "collector_tier", "target_minerals", "discarded_value_now_screen", "ebay_crossref_status", "ebay_market_evidence", "ebay_search_query", "ebay_search_url", "ebay_example_urls", "screening_basis", "dev_status", "operation_type", "underground_workings_screen", "commodity_codes", "commodities", "production_years", "land_status_mrds", "workings", "claim_status_note", "legal_caution"]
    with (out_dir / "az_collector_mineral_targets_ranked.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for feature in records:
            writer.writerow({k: feature["properties"].get(k, "") for k in fields})
    def rows(p): return "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(p.get(k, '')))}</td></tr>" for k in fields if p.get(k) not in (None, ""))
    kml = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Arizona collector mineral targets with eBay cross references</name>'
    for feature in records[:500]:
        p = feature["properties"]; lon, lat = feature["geometry"]["coordinates"][:2]
        kml += f"<Placemark><name>{html.escape(str(p.get('rank_collector')) + '. ' + str(p.get('name')))}</name><description><![CDATA[<table>{rows(p)}</table>]]></description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
    kml += "</Document></kml>"
    kml_path = out_dir / "az_collector_mineral_targets.kml"
    kml_path.write_text(kml, encoding="utf-8")
    make_kmz(kml_path, out_dir / "az_collector_mineral_targets.kmz")
    summary = {
        "generated": BUILD_DATE,
        "collector_targets": len(records),
        "tier_counts": dict(Counter(f["properties"].get("collector_tier") for f in records)),
        "theme_counts": {k: len(v) for k, v in sorted(by_theme.items())},
        "ebay_crossref_counts": dict(Counter(f["properties"].get("ebay_crossref_status") for f in records)),
        "caution": "Screening only; not proof of specimens, claimability, access, land status, or safety.",
    }
    (out_dir / "build_summary_collector_mineral_targets.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-mrds", required=True, help="Path to mrds_arizona_raw.geojson")
    parser.add_argument("--out", default="az_collector_mineral_targets")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw_mrds).read_text(encoding="utf-8"))["features"]
    records = build_targets(raw)
    write_outputs(records, Path(args.out))


if __name__ == "__main__":
    main()
