#!/usr/bin/env python3
"""Arizona gold GIS screening pipeline.

Standard-library script for the workflows built in Codex:
- fetch Arizona MRDS records
- screen WWII-window past-producing gold mines
- query live BLM active mining-claim polygons
- build statewide predictive gold target layers

All outputs are screening products only, not legal claimability, access, safety,
or proof-of-gold determinations.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

BUILD_DATE = "2026-05-03"
AZ_BBOX = "-115.1,31.2,-109.0,37.1"
MRDS_URL = "https://energy.usgs.gov/arcgis/rest/services/MRData/Mineral_Resource_Data_System/OGCFeatureServer/collections/3/items"
BLM_URL = "https://gis.blm.gov/nlsdb/rest/services/Mining_Claims/MiningClaims/MapServer"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TYPE_LABELS = {"384101": "Lode claim", "384201": "Placer claim", "384301": "Mill site", "384401": "Tunnel site"}


def request_json(url: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def qurl(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def first_dict(v) -> dict:
    vals = as_list(v)
    return vals[0] if vals and isinstance(vals[0], dict) else {}


def parsed(feature: dict) -> dict:
    try:
        return json.loads(feature.get("properties", {}).get("json") or "{}")
    except Exception:
        return {}


def props(feature: dict) -> dict:
    return parsed(feature).get("properties", {})


def geom(feature: dict) -> dict | None:
    return feature.get("geometry") or parsed(feature).get("geometry")


def flatten(v):
    if isinstance(v, dict):
        for item in v.values():
            yield from flatten(item)
    elif isinstance(v, list):
        for item in v:
            yield from flatten(item)
    elif v is not None:
        yield str(v)


def commodities(p: dict) -> list[dict]:
    out = []
    for c in as_list(p.get("commodity")):
        if isinstance(c, dict) and c.get("code"):
            out.append({"code": c.get("code"), "commodity": c.get("commod"), "importance": c.get("import")})
    return out


def gold_importance(p: dict) -> str:
    vals = [c.get("importance") or "" for c in commodities(p) if c.get("code") == "AU"]
    order = {"Primary": 3, "Secondary": 2, "Tertiary": 1}
    return sorted(vals, key=lambda x: order.get(x, 0), reverse=True)[0] if vals else ""


def years(values, keys: list[str]) -> list[int]:
    out = []
    for item in as_list(values):
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value and re.fullmatch(r"\d{4}", str(value)):
                    out.append(int(value))
    return out


def workings(p: dict) -> list[str]:
    rows = []
    for w in as_list(p.get("workings")):
        if not isinstance(w, dict):
            continue
        parts = []
        for key, label in [("wrk_tp", "type"), ("depth", "depth"), ("len", "length"), ("ovr_len", "overall_length"), ("ovr_wid", "overall_width"), ("area", "area")]:
            if w.get(key):
                parts.append(f"{label}={w[key]}")
        if parts:
            rows.append("; ".join(parts))
    return rows


def comments(p: dict) -> list[str]:
    return [f"{c.get('ctg') or 'Comment'}: {c.get('cmt_txt')}" for c in as_list(p.get("comment")) if isinstance(c, dict) and c.get("cmt_txt")]


def snippet(parts: list[str], max_len: int = 700) -> str:
    return re.sub(r"\s+", " ", " | ".join(x for x in parts if x)).strip()[:max_len]


def underground_status(p: dict, dep: dict) -> str:
    op = (dep.get("oper_tp") or "").lower()
    wrk = " ".join(workings(p)).lower()
    text = " ".join(flatten(p)).lower()
    underground_terms = ["underground", "shaft", "adit", "tunnel", "drift", "winze", "stope"]
    if "underground" in op or any(t in wrk for t in underground_terms):
        return "YES"
    if dep.get("oper_tp") and "surface" in op and "underground" not in op:
        return "NO_SURFACE_ONLY_IN_MRDS"
    if any(t in text for t in ["shaft", "adit", "tunnel", "drift", "stope"]):
        return "YES_TEXT_EVIDENCE"
    return "UNKNOWN_NOT_STATED_IN_MRDS"


def write_geojson(path: Path, features: list[dict], name: str) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "name": name, "generated": BUILD_DATE, "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")


def make_kmz(kml_path: Path, kmz_path: Path) -> None:
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(kml_path, arcname="doc.kml")


def esc(v) -> str:
    return html.escape(str(v) if v is not None else "")


def kml_rows(p: dict, keys: list[str] | None = None) -> str:
    keys = keys or list(p.keys())
    return "".join(f"<tr><th>{esc(k)}</th><td>{esc(p.get(k, ''))}</td></tr>" for k in keys if p.get(k) not in (None, ""))


def ring_coords(ring: list[list[float]]) -> str:
    return " ".join(f"{x},{y},0" for x, y in ring)


def polygon_kml(g: dict) -> str:
    if not g:
        return ""
    polys = [g.get("coordinates", [])] if g.get("type") == "Polygon" else g.get("coordinates", [])
    blocks = []
    for poly in polys:
        if not poly:
            continue
        inners = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{ring_coords(r)}</coordinates></LinearRing></innerBoundaryIs>" for r in poly[1:])
        blocks.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring_coords(poly[0])}</coordinates></LinearRing></outerBoundaryIs>{inners}</Polygon>")
    return "<MultiGeometry>" + "".join(blocks) + "</MultiGeometry>" if len(blocks) > 1 else "".join(blocks)


def envelope(lon: float, lat: float, radius_miles: float) -> dict:
    km = radius_miles * 1.609344
    dlat = km / 111.32
    dlon = km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    return {"xmin": lon - dlon, "ymin": lat - dlat, "xmax": lon + dlon, "ymax": lat + dlat, "spatialReference": {"wkid": 4326}}


def circle(lon: float, lat: float, radius_m: float, steps: int = 72) -> list[list[float]]:
    pts = []
    for i in range(steps + 1):
        b = 2 * math.pi * i / steps
        pts.append([lon + (radius_m / (111320 * max(0.2, math.cos(math.radians(lat))))) * math.sin(b), lat + (radius_m / 111320) * math.cos(b)])
    return pts


def fetch_mrds(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    features = []
    for offset in range(0, 40000, 10000):
        data = request_json(qurl(MRDS_URL, {"f": "json", "limit": "10000", "offset": str(offset), "bbox": AZ_BBOX}), timeout=240)
        batch = data.get("features", [])
        features.extend(batch)
        print(f"fetched offset {offset}: {len(batch)}")
        if len(batch) < 10000:
            break
    write_geojson(out / "mrds_arizona_raw.geojson", features, "mrds_arizona_raw")
    print(json.dumps({"raw_mrds_features": len(features), "out": str(out)}, indent=2))


def to_gold_record(feature: dict) -> dict | None:
    p = props(feature); g = geom(feature); loc = first_dict(p.get("location"))
    if loc.get("state_prov") != "Arizona" or not g:
        return None
    gi = gold_importance(p)
    if not gi and " AU " not in (feature.get("properties", {}).get("code_list") or ""):
        return None
    dep = p.get("deposits") if isinstance(p.get("deposits"), dict) else {}
    prod = years(p.get("production"), ["yr", "yr_ba"])
    own = years(p.get("ownership"), ["beg_yr", "end_yr", "info_yr"])
    names = [n.get("name") for n in as_list(p.get("name")) if isinstance(n, dict) and n.get("name")]
    name = names[0] if names else feature.get("properties", {}).get("site_name")
    return {"type": "Feature", "geometry": g, "properties": {
        "name": name, "county": loc.get("county"), "district": first_dict(p.get("districts")).get("district"),
        "mrds_dep_id": feature.get("properties", {}).get("dep_id"), "mrds_url": feature.get("properties", {}).get("url"),
        "dev_status": feature.get("properties", {}).get("dev_stat") or dep.get("dev_st"), "gold_importance": gi or "AU code present",
        "commodity_codes": (feature.get("properties", {}).get("code_list") or "").strip(),
        "commodities": "; ".join(f"{c['code']} {c.get('commodity') or ''} ({c.get('importance') or 'unknown'})" for c in commodities(p)),
        "operation_type": dep.get("oper_tp"), "deposit_type": dep.get("dep_tp"), "underground_workings_screen": underground_status(p, dep),
        "production_years": ", ".join(map(str, sorted(set(prod)))), "ownership_info_years": ", ".join(map(str, sorted(set(own)))),
        "ww2_window_years": ", ".join(map(str, sorted({y for y in prod + own if 1942 <= y <= 1945}))),
        "land_status_mrds": first_dict(p.get("land_status")).get("land_st"), "workings": snippet(workings(p), 500), "notes": snippet(comments(p), 700),
        "legal_caution": "Screening only; verify claims, land status, access, patents/private land, withdrawals, and safety."}}


def ww2_screen(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))["features"]
    gold = [r for r in (to_gold_record(f) for f in raw) if r]
    selected = []
    for r in gold:
        p = r["properties"]
        if p.get("dev_status") != "Past Producer":
            continue
        ys = [int(y) for field in ["production_years", "ownership_info_years"] for y in p.get(field, "").replace(",", " ").split() if y.isdigit()]
        if any(1942 <= y <= 1945 for y in ys) and not any(1946 <= y <= 1999 for y in ys):
            p["screening_result"] = "MRDS Past Producer gold record with 1942-1945 year and no parsed post-1945 operation year."
            selected.append(r)
    write_geojson(out / "az_all_mrds_gold_records.geojson", gold, "az_all_mrds_gold_records")
    write_geojson(out / "az_ww2_shutdown_never_reopened_gold_mines_all_screened.geojson", selected, "az_ww2_shutdown_never_reopened_gold_mines_all_screened")
    with (out / "az_ww2_shutdown_never_reopened_gold_mines_all_screened.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["name", "county", "district", "mrds_dep_id", "mrds_url", "dev_status", "gold_importance", "operation_type", "underground_workings_screen", "ww2_window_years", "land_status_mrds", "legal_caution"]
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        for f in selected: w.writerow({k: f["properties"].get(k, "") for k in fields})
    kml = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
    for f in selected:
        p = f["properties"]; lon, lat = f["geometry"]["coordinates"][:2]
        kml += f"<Placemark><name>{esc(p.get('name'))}</name><description><![CDATA[<table>{kml_rows(p)}</table>]]></description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
    kml += "</Document></kml>"
    kml_path = out / "az_ww2_shutdown_never_reopened_gold_mines.kml"; kml_path.write_text(kml, encoding="utf-8"); make_kmz(kml_path, out / "az_ww2_shutdown_never_reopened_gold_mines.kmz")
    print(json.dumps({"gold_records": len(gold), "ww2_screened": len(selected), "out": str(out)}, indent=2))


def query_active(lon: float, lat: float, radius_miles: float) -> list[dict]:
    fields = "OBJECTID,ADMIN_STATE,GEO_STATE,BLM_PROD,CSE_DISP,CSE_TYPE_NR,CSE_NR,LEG_CSE_NR,CSE_NAME,SRC,QLTY,CSE_META,RCRD_ACRS,SF_ID,REC_TYPE_CSE_GRP,MC_PATENTED,MC_EXCLUDED,MC_CONVEYED"
    params = {"f": "geojson", "where": "1=1", "geometry": json.dumps(envelope(lon, lat, radius_miles), separators=(",", ":")), "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "true", "outSR": "4326", "resultRecordCount": "2000"}
    url = qurl(f"{BLM_URL}/1/query", params)
    last = None
    for attempt in range(6):
        try:
            data = request_json(url, timeout=180)
            if "error" in data: raise RuntimeError(data["error"])
            return data.get("features", [])
        except Exception as exc:
            last = exc; time.sleep(3 * (attempt + 1))
    raise RuntimeError(str(last))


def live_claims(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    mines = json.loads(Path(args.mine_points).read_text(encoding="utf-8"))["features"]
    boundary_by_key, by_mine, errors = {}, defaultdict(list), {}
    for i, mine in enumerate(mines, 1):
        p = mine["properties"]; dep = p.get("mrds_dep_id"); lon, lat = mine["geometry"]["coordinates"][:2]
        try: claims = query_active(lon, lat, args.radius_miles)
        except Exception as exc: errors[dep] = str(exc); claims = []
        for claim in claims:
            cp = dict(claim.get("properties", {})); key = str(cp.get("OBJECTID") or cp.get("CSE_NR") or cp.get("LEG_CSE_NR") or id(claim)); by_mine[dep].append(key)
            if key not in boundary_by_key:
                cp["claim_type_label"] = TYPE_LABELS.get(str(cp.get("CSE_TYPE_NR")), str(cp.get("CSE_TYPE_NR") or "Unknown")); cp["recorded_claim_acres"] = cp.get("RCRD_ACRS")
                cp["matched_mrds_dep_ids"] = dep or ""; cp["matched_mine_names"] = p.get("name") or ""; cp["live_status_query_date"] = BUILD_DATE; cp["screening_radius_miles"] = args.radius_miles
                cp["claim_boundary_caution"] = "Screening only; BLM claim geometry may not be exact staked boundaries."
                claim["properties"] = cp; boundary_by_key[key] = claim
        print(f"{i}/{len(mines)} {p.get('name')}: {len(claims)} live active claims")
    boundaries = list(boundary_by_key.values())
    points = []
    for mine in mines:
        p = mine["properties"]; dep = p.get("mrds_dep_id"); claims = [boundary_by_key[k] for k in by_mine.get(dep, []) if k in boundary_by_key]
        acres = []
        for c in claims:
            try: acres.append(float(c["properties"].get("RCRD_ACRS")))
            except Exception: pass
        status = "LIVE_ACTIVE_BLM_CLAIMS_WITHIN_SCREEN" if claims else ("LIVE_CLAIM_QUERY_ERROR" if dep in errors else "NO_LIVE_ACTIVE_BLM_CLAIMS_FOUND_WITHIN_SCREEN")
        points.append({"type": "Feature", "geometry": mine["geometry"], "properties": {"name": p.get("name"), "county": p.get("county"), "district": p.get("district"), "mrds_dep_id": dep, "mrds_url": p.get("mrds_url"), "live_current_claim_status": status, "live_active_claim_boundary_count": len(claims), "live_active_claim_acres_total": round(sum(acres), 3) if acres else 0, "live_active_claim_acres_max": round(max(acres), 3) if acres else "", "live_query_error": errors.get(dep, ""), "claim_status_caution": "Live GIS screening only; verify MLRS, county records, land status, patents/private land, withdrawals, access, and monuments."}})
    write_geojson(out / "az_live_claim_status_mine_points.geojson", points, "az_live_claim_status_mine_points"); write_geojson(out / "az_live_active_claim_boundaries.geojson", boundaries, "az_live_active_claim_boundaries")
    print(json.dumps({"mine_points": len(points), "unique_live_active_claim_boundaries": len(boundaries), "status_counts": dict(Counter(f["properties"]["live_current_claim_status"] for f in points)), "query_errors": errors}, indent=2))


def dist_km(a, b) -> float:
    lon1, lat1 = a; lon2, lat2 = b
    x = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2)); y = (lat2 - lat1) * 111.32
    return (x * x + y * y) ** 0.5


def predict_statewide(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))["features"]
    records = []
    for f in raw:
        r = to_gold_record(f)
        if not r: continue
        p = r["properties"]; text = (p.get("notes", "") + " " + p.get("workings", "")).lower(); score = 0; reasons = []
        gi = p.get("gold_importance")
        if gi == "Primary": score += 32; reasons.append("gold is primary commodity")
        elif gi == "Secondary": score += 22; reasons.append("gold is secondary commodity")
        else: score += 12; reasons.append("gold present")
        if p.get("dev_status") == "Producer": score += 28; reasons.append("MRDS producer")
        elif p.get("dev_status") == "Past Producer": score += 25; reasons.append("MRDS past producer")
        elif p.get("dev_status") == "Prospect": score += 12; reasons.append("MRDS prospect")
        if str(p.get("underground_workings_screen", "")).startswith("YES"): score += 14; reasons.append("underground/shaft/tunnel evidence")
        if p.get("production_years"): score += 10; reasons.append("production year data present")
        if re.search(r"placer|alluvial|gravel|wash|gulch|creek", text): score += 8; reasons.append("placer/alluvial terms")
        if re.search(r"vein|quartz|shear|fault|lode|breccia", text): score += 8; reasons.append("lode/vein/structure terms")
        p["prediction_score_base"] = score; p["prediction_basis_base"] = "; ".join(reasons); records.append(r)
    grid, cell = defaultdict(list), 0.08
    for i, f in enumerate(records):
        lon, lat = f["geometry"]["coordinates"][:2]; grid[(int(lon / cell), int(lat / cell))].append(i)
    for i, f in enumerate(records):
        lon, lat = f["geometry"]["coordinates"][:2]; cx, cy = int(lon / cell), int(lat / cell); nearby = producers = 0
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for j in grid.get((cx + dx, cy + dy), []):
                    if i != j and dist_km((lon, lat), records[j]["geometry"]["coordinates"][:2]) <= 5:
                        nearby += 1; producers += records[j]["properties"].get("dev_status") in ["Producer", "Past Producer"]
        bonus = min(20, nearby * 1.2 + producers * 1.5); p = f["properties"]
        p["nearby_gold_records_5km"] = nearby; p["nearby_producer_records_5km"] = producers; p["density_bonus"] = round(bonus, 1)
        p["prediction_score"] = round(p.pop("prediction_score_base") + bonus, 1); p["prediction_basis"] = p.pop("prediction_basis_base") + f"; {nearby} nearby gold records within 5km"
        p["prediction_tier"] = "HIGH" if p["prediction_score"] >= 95 else ("MEDIUM" if p["prediction_score"] >= 70 else "LOW")
        p["prediction_caution"] = "Predictive screening only; not proof of gold, claimability, access, or safety."
    records.sort(key=lambda f: f["properties"]["prediction_score"], reverse=True)
    for rank, f in enumerate(records, 1): f["properties"]["rank_statewide"] = rank
    top = records[:750]
    zones = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [circle(*f["geometry"]["coordinates"][:2], 1609)]}, "properties": dict(f["properties"])} for f in records[:300]]
    write_geojson(out / "az_statewide_gold_prediction_all_mrds_gold_points.geojson", records, "az_statewide_gold_prediction_all_mrds_gold_points"); write_geojson(out / "az_statewide_gold_prediction_top750_points.geojson", top, "az_statewide_gold_prediction_top750_points"); write_geojson(out / "az_statewide_gold_prediction_top300_zones.geojson", zones, "az_statewide_gold_prediction_top300_zones")
    with (out / "az_statewide_gold_prediction_ranked_top1000.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["rank_statewide", "name", "county", "district", "mrds_dep_id", "mrds_url", "prediction_score", "prediction_tier", "prediction_basis", "dev_status", "gold_importance", "operation_type", "underground_workings_screen", "nearby_gold_records_5km", "land_status_mrds", "prediction_caution"]
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); [w.writerow({k: f["properties"].get(k, "") for k in fields}) for f in records[:1000]]
    print(json.dumps({"all_gold_records": len(records), "top_points": len(top), "top_zones": len(zones), "tier_counts": dict(Counter(f["properties"]["prediction_tier"] for f in records))}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch-mrds"); p.add_argument("--out", default="az_gold_outputs")
    p = sub.add_parser("ww2-screen"); p.add_argument("--raw", required=True); p.add_argument("--out", default="az_gold_outputs")
    p = sub.add_parser("live-claims"); p.add_argument("--mine-points", required=True); p.add_argument("--out", default="az_live_claim_status"); p.add_argument("--radius-miles", type=float, default=1.0)
    p = sub.add_parser("predict-statewide"); p.add_argument("--raw", required=True); p.add_argument("--out", default="az_statewide_gold_predictions")
    args = parser.parse_args()
    {"fetch-mrds": fetch_mrds, "ww2-screen": ww2_screen, "live-claims": live_claims, "predict-statewide": predict_statewide}[args.cmd](args)


if __name__ == "__main__":
    main()
