#!/usr/bin/env python3
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

USER_AGENT = "Codex-AZ-Mine-Tunnel-Mapper/1.0 (non-commercial educational use)"

OUT_BASE = Path("/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers") / f"az_mine_tunnels_portals_{datetime.now().strftime('%Y-%m-%d')}"


def http_get_json(url: str, params: Dict[str, str]) -> Any:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, data: str) -> Any:
    req = urllib.request.Request(
        url,
        data=data.encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def overpass_query(query: str, retries: int = 4) -> Dict[str, Any]:
    last_err = None
    for i in range(retries):
        try:
            return http_post_json(OVERPASS_URL, f"data={urllib.parse.quote(query)}")
        except Exception as e:
            last_err = e
            time.sleep(2 + i * 2)
    raise RuntimeError(f"Overpass query failed after {retries} attempts: {last_err}")


def to_feature(geom_type: str, coords: Any, props: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": geom_type, "coordinates": coords},
        "properties": props,
    }


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def point_to_segment_distance_m(px, py, ax, ay, bx, by):
    # Equirectangular approximation near Arizona latitudes.
    lat0 = math.radians((py + ay + by) / 3.0)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111320.0 * math.cos(lat0)

    p = ((px) * m_per_deg_lon, (py) * m_per_deg_lat)
    a = ((ax) * m_per_deg_lon, (ay) * m_per_deg_lat)
    b = ((bx) * m_per_deg_lon, (by) * m_per_deg_lat)

    vx = b[0] - a[0]
    vy = b[1] - a[1]
    wx = p[0] - a[0]
    wy = p[1] - a[1]
    vlen2 = vx * vx + vy * vy
    if vlen2 == 0:
        dx = p[0] - a[0]
        dy = p[1] - a[1]
        return math.sqrt(dx * dx + dy * dy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vlen2))
    cx = a[0] + t * vx
    cy = a[1] + t * vy
    dx = p[0] - cx
    dy = p[1] - cy
    return math.sqrt(dx * dx + dy * dy)


def nearest_tunnel_id(point_lon, point_lat, tunnel_features: List[Dict[str, Any]]) -> Tuple[str, float]:
    best_id = ""
    best_d = 1e18
    for ft in tunnel_features:
        coords = ft["geometry"]["coordinates"]
        props = ft["properties"]
        tid = props.get("feature_id", "")
        for i in range(len(coords) - 1):
            ax, ay = coords[i]
            bx, by = coords[i + 1]
            d = point_to_segment_distance_m(point_lon, point_lat, ax, ay, bx, by)
            if d < best_d:
                best_d = d
                best_id = tid
    return best_id, best_d


def clean_props(tags: Dict[str, str], extras: Dict[str, Any]) -> Dict[str, Any]:
    props = {}
    for k, v in (tags or {}).items():
        k2 = re.sub(r"[^A-Za-z0-9_]+", "_", k).strip("_").lower()
        if not k2:
            continue
        props[k2[:60]] = v
    props.update(extras)
    return props


def parse_overpass_elements(data: Dict[str, Any], source_label: str) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
    nodes = {}
    tunnel_lines = []
    portals = []
    addits = []
    stopes = []

    for e in data.get("elements", []):
        if e.get("type") == "node":
            nodes[e["id"]] = (e.get("lon"), e.get("lat"), e.get("tags", {}))

    for e in data.get("elements", []):
        et = e.get("type")
        tags = e.get("tags", {})
        fid = f"osm_{et}_{e.get('id')}"

        if et == "way" and "geometry" in e:
            coords = [[p["lon"], p["lat"]] for p in e["geometry"]]
            if len(coords) >= 2 and (tags.get("tunnel") == "mine" or tags.get("mine") == "tunnel" or tags.get("man_made") == "adit"):
                tunnel_lines.append(to_feature("LineString", coords, clean_props(tags, {
                    "feature_id": fid,
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                })))

            # Some adits are mapped as short ways.
            if len(coords) >= 2 and tags.get("man_made") == "adit":
                mid_lon = sum(c[0] for c in coords) / len(coords)
                mid_lat = sum(c[1] for c in coords) / len(coords)
                addits.append(to_feature("Point", [mid_lon, mid_lat], clean_props(tags, {
                    "feature_id": fid + "_midpoint",
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                    "derived_from": fid,
                })))

        if et == "node":
            lon = e.get("lon")
            lat = e.get("lat")
            if lon is None or lat is None:
                continue

            mm = tags.get("man_made", "")
            mining = tags.get("mining", "")
            tunnel = tags.get("tunnel", "")
            name = (tags.get("name", "") or "").lower()

            is_portal = mm == "portal" or "portal" in name
            is_addit = mm == "adit" or "adit" in name
            is_stope = mm == "stope" or mining == "stope" or "stope" in name
            is_mineshaft = mm == "mineshaft"

            if is_portal:
                portals.append(to_feature("Point", [lon, lat], clean_props(tags, {
                    "feature_id": fid,
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                })))
            if is_addit:
                addits.append(to_feature("Point", [lon, lat], clean_props(tags, {
                    "feature_id": fid,
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                })))
            if is_stope:
                stopes.append(to_feature("Point", [lon, lat], clean_props(tags, {
                    "feature_id": fid,
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                })))

            # Mine shafts are useful as stope-like underground-working proxies if explicit stopes are sparse.
            if is_mineshaft:
                stopes.append(to_feature("Point", [lon, lat], clean_props(tags, {
                    "feature_id": fid,
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                    "stope_proxy": "mineshaft",
                })))

            # If node directly tagged tunnel=mine, keep as portal-ish point cue.
            if tunnel == "mine" and not is_portal:
                portals.append(to_feature("Point", [lon, lat], clean_props(tags, {
                    "feature_id": fid + "_tunnelcue",
                    "source_query": source_label,
                    "mapped_or_inferred": "mapped",
                    "portal_proxy": "tunnel_mine_node",
                })))

    return tunnel_lines, portals, addits, stopes


def dedupe_points(features: List[Dict[str, Any]], precision: int = 6) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        key = (round(lon, precision), round(lat, precision), f["properties"].get("man_made"), f["properties"].get("name"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def dedupe_lines(features: List[Dict[str, Any]], precision: int = 6) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for f in features:
        coords = f["geometry"]["coordinates"]
        key = tuple((round(c[0], precision), round(c[1], precision)) for c in coords)
        key_rev = tuple(reversed(key))
        if key in seen or key_rev in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def build_inferred_connectors(portals: List[Dict], addits: List[Dict], stopes: List[Dict], tunnels: List[Dict]) -> List[Dict]:
    inferred = []
    point_sets = [("portal", portals), ("addit", addits), ("stope", stopes)]

    for ptype, feats in point_sets:
        for f in feats:
            lon, lat = f["geometry"]["coordinates"]
            src_id = f["properties"].get("feature_id", "")
            tid, dist_m = nearest_tunnel_id(lon, lat, tunnels) if tunnels else ("", 1e18)
            if tid and dist_m <= 1200:
                # Connect point to nearest endpoint of matched tunnel for visual association.
                t = next((x for x in tunnels if x["properties"].get("feature_id") == tid), None)
                if not t:
                    continue
                tcoords = t["geometry"]["coordinates"]
                ep1 = tcoords[0]
                ep2 = tcoords[-1]
                d1 = haversine_m(lat, lon, ep1[1], ep1[0])
                d2 = haversine_m(lat, lon, ep2[1], ep2[0])
                target = ep1 if d1 <= d2 else ep2
                inferred.append(to_feature("LineString", [[lon, lat], target], {
                    "feature_id": f"inferred_{ptype}_{src_id}",
                    "from_type": ptype,
                    "from_feature": src_id,
                    "to_tunnel": tid,
                    "distance_to_tunnel_m": round(dist_m, 1),
                    "mapped_or_inferred": "inferred",
                    "association_basis": "nearest_tunnel_within_1200m",
                }))

    # If still sparse, connect close portal-addit / portal-stope pairs.
    if len(inferred) < 4:
        for p in portals:
            plon, plat = p["geometry"]["coordinates"]
            pid = p["properties"].get("feature_id", "")
            candidates = addits + stopes
            best = None
            best_d = 1e18
            best_type = ""
            for c in candidates:
                clon, clat = c["geometry"]["coordinates"]
                d = haversine_m(plat, plon, clat, clon)
                if d < best_d:
                    best_d = d
                    best = c
                    best_type = "addit_or_stope"
            if best and best_d <= 1500:
                blon, blat = best["geometry"]["coordinates"]
                bid = best["properties"].get("feature_id", "")
                inferred.append(to_feature("LineString", [[plon, plat], [blon, blat]], {
                    "feature_id": f"inferred_pair_{pid}_{bid}",
                    "from_type": "portal",
                    "to_type": best_type,
                    "from_feature": pid,
                    "to_feature": bid,
                    "distance_m": round(best_d, 1),
                    "mapped_or_inferred": "inferred",
                    "association_basis": "nearest_portal_to_addit_or_stope_within_1500m",
                }))

    # If no mapped tunnel lines exist, synthesize tunnel-run cues by connecting nearby
    # underground-working points (addit<->stope / addit<->addit / stope<->stope).
    if not tunnels or len(inferred) < 8:
        point_pool = [("addit", f) for f in addits] + [("stope", f) for f in stopes]
        for idx, (ptype, f) in enumerate(point_pool):
            lon, lat = f["geometry"]["coordinates"]
            fid = f["properties"].get("feature_id", f"{ptype}_{idx}")
            best = None
            best_d = 1e18
            best_type = ""
            for jdx, (qtype, qf) in enumerate(point_pool):
                if idx == jdx:
                    continue
                qlon, qlat = qf["geometry"]["coordinates"]
                d = haversine_m(lat, lon, qlat, qlon)
                if d < best_d:
                    best_d = d
                    best = qf
                    best_type = qtype
            if best and 80 <= best_d <= 2200:
                blon, blat = best["geometry"]["coordinates"]
                bid = best["properties"].get("feature_id", best_type)
                inferred.append(to_feature("LineString", [[lon, lat], [blon, blat]], {
                    "feature_id": f"inferred_network_{fid}_{bid}",
                    "from_type": ptype,
                    "to_type": best_type,
                    "from_feature": fid,
                    "to_feature": bid,
                    "distance_m": round(best_d, 1),
                    "mapped_or_inferred": "inferred",
                    "association_basis": "nearest_underground_working_pair_80m_to_2200m",
                }))

    return dedupe_lines(inferred)


def write_geojson(path: Path, features: List[Dict[str, Any]]):
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, indent=2), encoding="utf-8")


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kml_placemark_for_feature(f: Dict[str, Any], style_url: str) -> str:
    g = f["geometry"]
    props = f.get("properties", {})
    name = props.get("name") or props.get("feature_id") or "feature"
    desc_lines = [f"{k}: {v}" for k, v in props.items() if v is not None]
    desc = "\\n".join(desc_lines)
    geom = ""

    if g["type"] == "Point":
        lon, lat = g["coordinates"]
        geom = f"<Point><coordinates>{lon},{lat},0</coordinates></Point>"
    elif g["type"] == "LineString":
        coords = " ".join(f"{c[0]},{c[1]},0" for c in g["coordinates"])
        geom = f"<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString>"
    else:
        return ""

    return (
        f"<Placemark><name>{esc(str(name))}</name>"
        f"<styleUrl>#{style_url}</styleUrl>"
        f"<description>{esc(desc)}</description>{geom}</Placemark>"
    )


def build_kml(layer_map: Dict[str, Tuple[List[Dict], str]]) -> str:
    styles = """
    <Style id="tunnelLine"><LineStyle><color>ff00ffff</color><width>3</width></LineStyle></Style>
    <Style id="inferredLine"><LineStyle><color>ff00a5ff</color><width>2</width></LineStyle></Style>
    <Style id="portalPoint"><IconStyle><color>ff0000ff</color><scale>1.1</scale></IconStyle></Style>
    <Style id="additPoint"><IconStyle><color>ff00ff00</color><scale>1.1</scale></IconStyle></Style>
    <Style id="stopePoint"><IconStyle><color>ffff00ff</color><scale>1.1</scale></IconStyle></Style>
    """

    folders = []
    for layer_name, (features, style_id) in layer_map.items():
        pms = [kml_placemark_for_feature(f, style_id) for f in features]
        pms = [x for x in pms if x]
        folders.append(f"<Folder><name>{esc(layer_name)}</name>{''.join(pms)}</Folder>")

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>"
        "<name>AZ Mine Tunnels, Portals, Addits, Stopes</name>"
        f"{styles}"
        f"{''.join(folders)}"
        "</Document></kml>"
    )


def write_kmz(kml_text: str, kmz_path: Path):
    import zipfile
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_text)


def query_county(county_name: str) -> Dict[str, Any]:
    q = f"""
[out:json][timeout:180];
area["name"="{county_name}"]["boundary"="administrative"]["admin_level"="6"]->.county;
(
  way(area.county)["tunnel"="mine"];
  way(area.county)["mine"="tunnel"];
  way(area.county)["man_made"="adit"];
  node(area.county)["man_made"="adit"];
  node(area.county)["man_made"="portal"];
  node(area.county)["man_made"="stope"];
  node(area.county)["mining"="stope"];
  node(area.county)["man_made"="mineshaft"];
  node(area.county)["tunnel"="mine"];
);
out body geom;
"""
    return overpass_query(q)


def geocode_lone_star() -> Tuple[float, float, str]:
    queries = [
        "Lone Star Mine, Arizona, USA",
        "Lone Star Mine, Graham County, Arizona, USA",
        "Lonestar Mine, Arizona, USA",
    ]
    for q in queries:
        res = http_get_json(NOMINATIM_URL, {"q": q, "format": "jsonv2", "limit": "1"})
        if res:
            lon = float(res[0]["lon"])
            lat = float(res[0]["lat"])
            display = res[0].get("display_name", q)
            return lat, lon, display
    raise RuntimeError("Could not geocode Lone Star Mine in Arizona")


def query_lone_star_area(lat: float, lon: float, radius_m: int = 8000) -> Dict[str, Any]:
    q = f"""
[out:json][timeout:180];
(
  way(around:{radius_m},{lat},{lon})["tunnel"="mine"];
  way(around:{radius_m},{lat},{lon})["mine"="tunnel"];
  way(around:{radius_m},{lat},{lon})["man_made"="adit"];
  node(around:{radius_m},{lat},{lon})["man_made"="adit"];
  node(around:{radius_m},{lat},{lon})["man_made"="portal"];
  node(around:{radius_m},{lat},{lon})["man_made"="stope"];
  node(around:{radius_m},{lat},{lon})["mining"="stope"];
  node(around:{radius_m},{lat},{lon})["man_made"="mineshaft"];
  node(around:{radius_m},{lat},{lon})["tunnel"="mine"];
);
out body geom;
"""
    return overpass_query(q)


def main():
    OUT_BASE.mkdir(parents=True, exist_ok=True)

    # Query counties.
    yav_data = query_county("Yavapai County")
    sc_data = query_county("Santa Cruz County")

    yav_t, yav_p, yav_a, yav_s = parse_overpass_elements(yav_data, "Yavapai County")
    sc_t, sc_p, sc_a, sc_s = parse_overpass_elements(sc_data, "Santa Cruz County")

    # Query and force-include Lone Star Mine area.
    ls_lat, ls_lon, ls_name = geocode_lone_star()
    ls_data = query_lone_star_area(ls_lat, ls_lon, radius_m=10000)
    ls_t, ls_p, ls_a, ls_s = parse_overpass_elements(ls_data, "Lone Star Mine Area")

    # Add explicit Lone Star marker point.
    lone_star_marker = to_feature("Point", [ls_lon, ls_lat], {
        "feature_id": "lone_star_mine_marker",
        "name": "Lone Star Mine (geocoded)",
        "display_name": ls_name,
        "source_query": "Nominatim",
        "mapped_or_inferred": "geocoded",
    })

    tunnel_lines = dedupe_lines(yav_t + sc_t + ls_t)
    portals = dedupe_points(yav_p + sc_p + ls_p + [lone_star_marker])
    addits = dedupe_points(yav_a + sc_a + ls_a)
    stopes = dedupe_points(yav_s + sc_s + ls_s)

    # Associate points to nearest tunnel.
    for coll in [portals, addits, stopes]:
        for f in coll:
            lon, lat = f["geometry"]["coordinates"]
            tid, d = nearest_tunnel_id(lon, lat, tunnel_lines) if tunnel_lines else ("", 1e18)
            if tid and d <= 1500:
                f["properties"]["associated_tunnel_id"] = tid
                f["properties"]["distance_to_tunnel_m"] = round(d, 1)

    inferred = build_inferred_connectors(portals, addits, stopes, tunnel_lines)

    # Write GeoJSON layers.
    write_geojson(OUT_BASE / "tunnel_lines.geojson", tunnel_lines)
    write_geojson(OUT_BASE / "portals.geojson", portals)
    write_geojson(OUT_BASE / "addits.geojson", addits)
    write_geojson(OUT_BASE / "stopes_or_stope_like.geojson", stopes)
    write_geojson(OUT_BASE / "inferred_tunnel_connectors.geojson", inferred)

    # Build layered KMZ.
    layer_map = {
        "01_mapped_tunnel_lines": (tunnel_lines, "tunnelLine"),
        "02_portals_and_lone_star_marker": (portals, "portalPoint"),
        "03_addits": (addits, "additPoint"),
        "04_stopes_or_stope_like": (stopes, "stopePoint"),
        "05_inferred_tunnel_connectors": (inferred, "inferredLine"),
    }
    kml = build_kml(layer_map)
    (OUT_BASE / "az_mine_tunnels_portals_addits_stopes_layers.kml").write_text(kml, encoding="utf-8")
    write_kmz(kml, OUT_BASE / "az_mine_tunnels_portals_addits_stopes_layers.kmz")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "output_directory": str(OUT_BASE),
        "counts": {
            "tunnel_lines": len(tunnel_lines),
            "portals": len(portals),
            "addits": len(addits),
            "stopes_or_stope_like": len(stopes),
            "inferred_tunnel_connectors": len(inferred),
        },
        "notes": [
            "Mapped geometries come from OpenStreetMap via Overpass for Yavapai and Santa Cruz counties plus a Lone Star Mine radius query.",
            "Inferred connectors are explicitly marked mapped_or_inferred=inferred and are association visuals, not surveyed underground alignments.",
            "This is screening-grade map data, not engineering or legal mine plans.",
        ],
    }
    (OUT_BASE / "build_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
