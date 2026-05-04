#!/usr/bin/env python3
"""Build public Arizona heritage and Spanish trail GeoJSON/KMZ layers."""

from __future__ import annotations

import html
import json
import os
import textwrap
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests


HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"

AZ_BBOX = (-114.9, 31.2, -109.0, 37.1)

OLD_SPANISH_URL = (
    "https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/"
    "OLSP_CAS_Line_201801/FeatureServer/0/query"
)
ANZA_RECREATION_URL = (
    "https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/"
    "JUBA_NHT_RECREATION_TRAILS_view/FeatureServer/0/query"
)


PUBLIC_INDIGENOUS_SITES = [
    {
        "name": "Casa Grande Ruins National Monument",
        "lon": -111.5355,
        "lat": 32.9954,
        "culture_period": "Hohokam / ancestral Sonoran Desert communities",
        "site_type": "managed national monument visitor site",
        "access_note": "Public NPS site; mapped at the visitor/monument area.",
        "source_url": "https://www.nps.gov/cagr/",
    },
    {
        "name": "Montezuma Castle National Monument",
        "lon": -111.8357,
        "lat": 34.6118,
        "culture_period": "Sinagua / ancestral Verde Valley communities",
        "site_type": "managed national monument visitor site",
        "access_note": "Public NPS site; mapped at the public visitor area.",
        "source_url": "https://www.nps.gov/moca/",
    },
    {
        "name": "Tuzigoot National Monument",
        "lon": -112.0274,
        "lat": 34.7723,
        "culture_period": "Sinagua / ancestral Verde Valley communities",
        "site_type": "managed national monument pueblo site",
        "access_note": "Public NPS site; mapped at the public visitor area.",
        "source_url": "https://www.nps.gov/tuzi/",
    },
    {
        "name": "Walnut Canyon National Monument",
        "lon": -111.5103,
        "lat": 35.1682,
        "culture_period": "Sinagua / ancestral Flagstaff-area communities",
        "site_type": "managed national monument cliff dwelling visitor site",
        "access_note": "Public NPS site; mapped at the public visitor area.",
        "source_url": "https://www.nps.gov/waca/",
    },
    {
        "name": "Wupatki National Monument",
        "lon": -111.3957,
        "lat": 35.5239,
        "culture_period": "Ancestral Puebloan and related descendant communities",
        "site_type": "managed national monument pueblo landscape",
        "access_note": "Public NPS site; mapped at the public visitor area.",
        "source_url": "https://www.nps.gov/wupa/",
    },
    {
        "name": "Navajo National Monument",
        "lon": -110.5364,
        "lat": 36.6769,
        "culture_period": "Ancestral Puebloan / descendant Tribal communities",
        "site_type": "managed national monument visitor area",
        "access_note": "Public NPS site; mapped at the visitor area, not closed ruins.",
        "source_url": "https://www.nps.gov/nava/",
    },
    {
        "name": "Canyon de Chelly National Monument Visitor Center",
        "lon": -109.5468,
        "lat": 36.1314,
        "culture_period": "Ancestral Puebloan, Hopi, Navajo, and other communities",
        "site_type": "managed national monument visitor area",
        "access_note": "Mapped at the public visitor center/overlook context.",
        "source_url": "https://www.nps.gov/cach/",
    },
    {
        "name": "Tonto National Monument",
        "lon": -111.1125,
        "lat": 33.6464,
        "culture_period": "Salado / ancestral Tonto Basin communities",
        "site_type": "managed national monument cliff dwelling visitor site",
        "access_note": "Public NPS site; mapped at the visitor area.",
        "source_url": "https://www.nps.gov/tont/",
    },
    {
        "name": "Homolovi State Park",
        "lon": -110.6529,
        "lat": 35.0807,
        "culture_period": "Hopi ancestral sites",
        "site_type": "managed state park archaeological landscape",
        "access_note": "Public Arizona State Parks site; respect signed closures.",
        "source_url": "https://azstateparks.com/homolovi",
    },
    {
        "name": "S'edav Va'aki Museum",
        "lon": -111.9863,
        "lat": 33.4457,
        "culture_period": "Ancestral O'Odham / Hohokam",
        "site_type": "city museum and archaeological park",
        "access_note": "Public museum/park in Phoenix.",
        "source_url": "https://www.phoenix.gov/parks/arts-culture-history/sedav-vaaki",
    },
    {
        "name": "Besh-Ba-Gowah Archaeological Park",
        "lon": -110.7815,
        "lat": 33.3943,
        "culture_period": "Salado / ancestral regional communities",
        "site_type": "city archaeological park",
        "access_note": "Public interpreted park in Globe.",
        "source_url": "https://www.globeaz.gov/visitors/besh-ba-gowah",
    },
    {
        "name": "Deer Valley Petroglyph Preserve",
        "lon": -112.1504,
        "lat": 33.6836,
        "culture_period": "Patayan, Hohokam, and Archaic traditions",
        "site_type": "managed petroglyph preserve",
        "access_note": "Public preserve with controlled access.",
        "source_url": "https://shesc.asu.edu/deer-valley-petroglyph-preserve",
    },
    {
        "name": "V-Bar-V Heritage Site",
        "lon": -111.7120,
        "lat": 34.6700,
        "culture_period": "Sinagua / Verde Valley rock art",
        "site_type": "managed heritage site",
        "access_note": "Public Coconino National Forest heritage site.",
        "source_url": "https://www.fs.usda.gov/recarea/coconino/recarea/?recid=55272",
    },
    {
        "name": "Palatki Heritage Site",
        "lon": -111.8980,
        "lat": 34.9150,
        "culture_period": "Sinagua / Verde Valley cliff dwellings and rock art",
        "site_type": "managed heritage site",
        "access_note": "Public managed Coconino National Forest site; reservations may apply.",
        "source_url": "https://www.fs.usda.gov/recarea/coconino/recarea/?recid=55368",
    },
    {
        "name": "Mesa Grande Cultural Park",
        "lon": -111.8378,
        "lat": 33.4236,
        "culture_period": "Ancestral O'Odham / Hohokam",
        "site_type": "city cultural park",
        "access_note": "Public city park and interpreted platform mound site.",
        "source_url": "https://www.mesaaz.gov/things-to-do/arts-culture/museums/mesa-grande-cultural-park",
    },
    {
        "name": "Casa Malpais Archaeological Park",
        "lon": -109.2767,
        "lat": 34.1296,
        "culture_period": "Mogollon / ancestral White Mountain communities",
        "site_type": "managed archaeological park",
        "access_note": "Public interpreted park in Springerville.",
        "source_url": "https://www.springervilleaz.gov/casa-malpais-archaeological-park/",
    },
    {
        "name": "Painted Rock Petroglyph Site",
        "lon": -113.0180,
        "lat": 33.0250,
        "culture_period": "Hohokam, Patayan, and other regional traditions",
        "site_type": "managed BLM petroglyph site",
        "access_note": "Public BLM site; stay on designated routes.",
        "source_url": "https://www.blm.gov/visit/painted-rock-petroglyph-site",
    },
    {
        "name": "Signal Hill Petroglyphs",
        "lon": -111.2167,
        "lat": 32.2470,
        "culture_period": "Hohokam / ancestral Sonoran Desert communities",
        "site_type": "managed national park visitor site",
        "access_note": "Public Saguaro National Park trail stop.",
        "source_url": "https://www.nps.gov/sagu/",
    },
]


SPANISH_COLONIAL_SITES = [
    {
        "name": "Tumacacori National Historical Park",
        "lon": -111.0517,
        "lat": 31.5687,
        "site_type": "Spanish colonial mission site / national historical park",
        "access_note": "Public NPS site on the Anza Trail corridor.",
        "source_url": "https://www.nps.gov/tuma/",
    },
    {
        "name": "Tubac Presidio State Historic Park",
        "lon": -111.0470,
        "lat": 31.6120,
        "site_type": "Spanish presidio / state historic park",
        "access_note": "Public Arizona State Parks site.",
        "source_url": "https://azstateparks.com/tubac",
    },
    {
        "name": "Mission San Xavier del Bac",
        "lon": -111.0071,
        "lat": 32.1078,
        "site_type": "Spanish colonial mission church",
        "access_note": "Public mission site on the Tohono O'odham Nation; follow local access rules.",
        "source_url": "https://sanxaviermission.org/",
    },
    {
        "name": "Presidio San Agustin del Tucson Museum",
        "lon": -110.9740,
        "lat": 32.2226,
        "site_type": "Spanish presidio museum",
        "access_note": "Public museum in downtown Tucson.",
        "source_url": "https://tucsonpresidio.com/",
    },
    {
        "name": "Yuma Crossing National Heritage Area",
        "lon": -114.6150,
        "lat": 32.7250,
        "site_type": "Colorado River crossing and colonial/territorial heritage area",
        "access_note": "Public heritage area connected to historic travel corridors.",
        "source_url": "https://www.yumaheritage.com/",
    },
    {
        "name": "Los Santos Angeles de Guevavi Mission Unit",
        "lon": -110.9676,
        "lat": 31.4580,
        "site_type": "Spanish colonial mission site / NPS unit",
        "access_note": "Managed Tumacacori NHP unit; public access may be guided or limited.",
        "source_url": "https://www.nps.gov/tuma/",
    },
    {
        "name": "Calabazas Mission Unit",
        "lon": -111.0600,
        "lat": 31.4970,
        "site_type": "Spanish colonial mission site / NPS unit",
        "access_note": "Managed Tumacacori NHP unit; public access may be guided or limited.",
        "source_url": "https://www.nps.gov/tuma/",
    },
]


def arcgis_geojson(url: str) -> dict[str, Any]:
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    response = requests.get(full_url, timeout=60)
    response.raise_for_status()
    return response.json()


def in_bbox(point: list[float] | tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    lon, lat = point[:2]
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def clip_line_to_bbox(coords: list[list[float]], bbox: tuple[float, float, float, float]) -> list[list[list[float]]]:
    segments: list[list[list[float]]] = []
    current: list[list[float]] = []
    for coord in coords:
        if in_bbox(coord, bbox):
            current.append([coord[0], coord[1]])
        elif current:
            if len(current) >= 2:
                segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)
    return segments


def clipped_geometry(geometry: dict[str, Any], bbox: tuple[float, float, float, float]) -> dict[str, Any] | None:
    if geometry["type"] == "LineString":
        segments = clip_line_to_bbox(geometry["coordinates"], bbox)
    elif geometry["type"] == "MultiLineString":
        segments = []
        for line in geometry["coordinates"]:
            segments.extend(clip_line_to_bbox(line, bbox))
    else:
        return geometry if geometry["type"] == "Point" and in_bbox(geometry["coordinates"], bbox) else None

    if not segments:
        return None
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": segments[0]}
    return {"type": "MultiLineString", "coordinates": segments}


def trail_layer(url: str, layer_name: str, source_url: str) -> dict[str, Any]:
    data = arcgis_geojson(url)
    features = []
    for feature in data.get("features", []):
        raw_geometry = feature.get("geometry")
        if not raw_geometry:
            continue
        geometry = clipped_geometry(raw_geometry, AZ_BBOX)
        if not geometry:
            continue
        props = dict(feature.get("properties") or {})
        props["layer"] = layer_name
        props["source_url"] = source_url
        props["accuracy_note"] = "Official public trail data, clipped approximately to an Arizona bounding box."
        features.append({"type": "Feature", "geometry": geometry, "properties": props})
    return {"type": "FeatureCollection", "features": features}


def point_layer(records: list[dict[str, Any]], layer_name: str) -> dict[str, Any]:
    features = []
    for record in records:
        props = {k: v for k, v in record.items() if k not in {"lon", "lat"}}
        props["layer"] = layer_name
        props["sensitivity_note"] = (
            "Public-facing managed site or visitor point; not a confidential archaeological coordinate."
        )
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [record["lon"], record["lat"]]},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_geojson(name: str, data: dict[str, Any]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def coordinates_text(coords: Iterable[list[float]]) -> str:
    return " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat, *_ in coords)


def placemark_for_feature(feature: dict[str, Any]) -> str:
    props = feature.get("properties") or {}
    name = str(props.get("name") or props.get("TRNAME") or props.get("MAPLABEL") or props.get("layer") or "Feature")
    description_parts = []
    for key in sorted(props):
        value = props[key]
        if value in (None, ""):
            continue
        description_parts.append(f"<b>{html.escape(str(key))}</b>: {html.escape(str(value))}")
    description = "<br/>".join(description_parts)
    geometry = feature["geometry"]

    if geometry["type"] == "Point":
        lon, lat = geometry["coordinates"][:2]
        geom_xml = f"<Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>"
    elif geometry["type"] == "LineString":
        geom_xml = (
            "<LineString><tessellate>1</tessellate><coordinates>"
            + coordinates_text(geometry["coordinates"])
            + "</coordinates></LineString>"
        )
    elif geometry["type"] == "MultiLineString":
        parts = []
        for line in geometry["coordinates"]:
            parts.append(
                "<LineString><tessellate>1</tessellate><coordinates>"
                + coordinates_text(line)
                + "</coordinates></LineString>"
            )
        geom_xml = "<MultiGeometry>" + "".join(parts) + "</MultiGeometry>"
    else:
        return ""

    return textwrap.dedent(
        f"""
        <Placemark>
          <name>{html.escape(name)}</name>
          <description><![CDATA[{description}]]></description>
          {geom_xml}
        </Placemark>
        """
    ).strip()


def write_kmz(name: str, layers: list[tuple[str, dict[str, Any]]]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    folders = []
    for folder_name, collection in layers:
        placemarks = "\n".join(placemark_for_feature(feature) for feature in collection["features"])
        folders.append(f"<Folder><name>{html.escape(folder_name)}</name>{placemarks}</Folder>")
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{html.escape(name.removesuffix('.kmz'))}</name>"
        + "".join(folders)
        + "</Document></kml>\n"
    )
    kmz_path = OUT_DIR / name
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    return kmz_path


def main() -> None:
    indigenous = point_layer(PUBLIC_INDIGENOUS_SITES, "Public Indigenous heritage sites")
    spanish_sites = point_layer(SPANISH_COLONIAL_SITES, "Spanish colonial public sites")
    old_spanish = trail_layer(
        OLD_SPANISH_URL,
        "Old Spanish National Historic Trail - Arizona",
        "https://www.nps.gov/olsp/",
    )
    anza = trail_layer(
        ANZA_RECREATION_URL,
        "Juan Bautista de Anza National Historic Trail - Arizona",
        "https://www.nps.gov/juba/",
    )

    layers = [
        ("Public Indigenous Heritage Sites", indigenous),
        ("Spanish Colonial Public Sites", spanish_sites),
        ("Old Spanish National Historic Trail - Arizona", old_spanish),
        ("Juan Bautista de Anza National Historic Trail - Arizona", anza),
    ]
    bundle = {
        "type": "FeatureCollection",
        "features": [feature for _, layer in layers for feature in layer["features"]],
    }

    paths = [
        write_geojson("az_public_indigenous_heritage_sites.geojson", indigenous),
        write_geojson("az_spanish_colonial_sites.geojson", spanish_sites),
        write_geojson("az_old_spanish_nht_arizona.geojson", old_spanish),
        write_geojson("az_anza_nht_arizona.geojson", anza),
        write_geojson("az_heritage_spanish_trails_bundle.geojson", bundle),
        write_kmz("az_public_indigenous_heritage_sites.kmz", [layers[0]]),
        write_kmz("az_spanish_colonial_sites.kmz", [layers[1]]),
        write_kmz("az_old_spanish_nht_arizona.kmz", [layers[2]]),
        write_kmz("az_anza_nht_arizona.kmz", [layers[3]]),
        write_kmz("az_heritage_spanish_trails_bundle.kmz", layers),
    ]

    summary = {
        "feature_counts": {folder: len(layer["features"]) for folder, layer in layers},
        "outputs": [os.fspath(path.relative_to(HERE)) for path in paths],
        "notes": [
            "Public interpreted/managed sites only.",
            "Trail lines use official NPS ArcGIS feature services and are clipped approximately to Arizona.",
        ],
    }
    write_geojson("build_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
