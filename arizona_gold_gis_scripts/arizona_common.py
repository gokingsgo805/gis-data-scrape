#!/usr/bin/env python3
"""Shared helpers for Arizona gold GIS screening scripts."""

from __future__ import annotations

import html
import json
import math
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = {"User-Agent": "Mozilla/5.0"}

MRDS_ITEMS_URL = (
    "https://energy.usgs.gov/arcgis/rest/services/MRData/"
    "Mineral_Resource_Data_System/OGCFeatureServer/collections/3/items"
)

BLM_CLAIMS_URL = (
    "https://gis.blm.gov/nlsdb/rest/services/Mining_Claims/"
    "MiningClaims/MapServer"
)

TYPE_LABELS = {
    "384101": "Lode claim",
    "384201": "Placer claim",
    "384301": "Mill site",
    "384401": "Tunnel site",
}


def request_json(url: str, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def query_url(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def as_list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def first_dict(value) -> dict:
    values = as_list(value)
    return values[0] if values and isinstance(values[0], dict) else {}


def parse_mrds_payload(feature: dict) -> dict:
    try:
        return json.loads(feature.get("properties", {}).get("json") or "{}")
    except Exception:
        return {}


def mrds_properties(feature: dict) -> dict:
    return parse_mrds_payload(feature).get("properties", {})


def mrds_geometry(feature: dict) -> dict | None:
    return feature.get("geometry") or parse_mrds_payload(feature).get("geometry")


def flatten(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from flatten(item)
    elif value is not None:
        yield str(value)


def commodities(props: dict) -> list[dict]:
    values = []
    for commodity in as_list(props.get("commodity")):
        if isinstance(commodity, dict) and commodity.get("code"):
            values.append(
                {
                    "code": commodity.get("code"),
                    "commodity": commodity.get("commod"),
                    "importance": commodity.get("import"),
                }
            )
    return values


def gold_importance(props: dict) -> str:
    values = [
        item.get("importance") or ""
        for item in commodities(props)
        if item.get("code") == "AU"
    ]
    order = {"Primary": 3, "Secondary": 2, "Tertiary": 1}
    return sorted(values, key=lambda value: order.get(value, 0), reverse=True)[0] if values else ""


def extract_years(values, keys: list[str]) -> list[int]:
    years = []
    for item in as_list(values):
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if value and re.fullmatch(r"\d{4}", str(value)):
                years.append(int(value))
    return years


def workings_summary(props: dict) -> list[str]:
    rows = []
    for item in as_list(props.get("workings")):
        if not isinstance(item, dict):
            continue
        parts = []
        for key, label in [
            ("wrk_tp", "type"),
            ("depth", "depth"),
            ("len", "length"),
            ("ovr_len", "overall_length"),
            ("ovr_wid", "overall_width"),
            ("area", "area"),
        ]:
            if item.get(key):
                parts.append(f"{label}={item[key]}")
        if parts:
            rows.append("; ".join(parts))
    return rows


def underground_status(props: dict, deposit: dict) -> str:
    op_type = (deposit.get("oper_tp") or "").lower()
    workings = " ".join(workings_summary(props)).lower()
    text = " ".join(flatten(props)).lower()
    underground_terms = ["underground", "shaft", "adit", "tunnel", "drift", "winze", "stope"]
    if "underground" in op_type or any(term in workings for term in underground_terms):
        return "YES"
    if deposit.get("oper_tp") and "surface" in op_type and "underground" not in op_type:
        return "NO_SURFACE_ONLY_IN_MRDS"
    if any(term in text for term in ["shaft", "adit", "tunnel", "drift", "stope"]):
        return "YES_TEXT_EVIDENCE"
    return "UNKNOWN_NOT_STATED_IN_MRDS"


def snippet(parts: list[str], max_len: int = 700) -> str:
    return re.sub(r"\s+", " ", " | ".join(part for part in parts if part)).strip()[:max_len]


def comments(props: dict) -> list[str]:
    rows = []
    for item in as_list(props.get("comment")):
        if isinstance(item, dict) and item.get("cmt_txt"):
            rows.append(f"{item.get('ctg') or 'Comment'}: {item.get('cmt_txt')}")
    return rows


def envelope(lon: float, lat: float, radius_miles: float) -> dict:
    radius_km = radius_miles * 1.609344
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    return {
        "xmin": lon - dlon,
        "ymin": lat - dlat,
        "xmax": lon + dlon,
        "ymax": lat + dlat,
        "spatialReference": {"wkid": 4326},
    }


def circle(lon: float, lat: float, radius_m: float, steps: int = 72) -> list[list[float]]:
    points = []
    for i in range(steps + 1):
        bearing = 2 * math.pi * i / steps
        dlat = (radius_m / 111320.0) * math.cos(bearing)
        dlon = (radius_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))) * math.sin(bearing)
        points.append([lon + dlon, lat + dlat])
    return points


def write_geojson(path: Path, features: list[dict], name: str, generated: str) -> None:
    payload = {"type": "FeatureCollection", "name": name, "generated": generated, "features": features}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def esc(value) -> str:
    return html.escape(str(value) if value is not None else "")


def kml_row(key: str, value) -> str:
    if value in (None, ""):
        return ""
    return f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>"


def ring_coordinates(ring: list[list[float]]) -> str:
    return " ".join(f"{x},{y},0" for x, y in ring)


def polygon_kml(geometry: dict) -> str:
    if not geometry:
        return ""
    polygons = [geometry.get("coordinates", [])] if geometry.get("type") == "Polygon" else geometry.get("coordinates", [])
    blocks = []
    for polygon in polygons:
        if not polygon:
            continue
        outer = ring_coordinates(polygon[0])
        inners = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{ring_coordinates(ring)}</coordinates></LinearRing></innerBoundaryIs>"
            for ring in polygon[1:]
        )
        blocks.append(
            f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{inners}</Polygon>"
        )
    return f"<MultiGeometry>{''.join(blocks)}</MultiGeometry>" if len(blocks) > 1 else "".join(blocks)


def make_kmz(kml_path: Path, kmz_path: Path) -> None:
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(kml_path, arcname="doc.kml")
