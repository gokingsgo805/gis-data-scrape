#!/usr/bin/env python3
"""Build generalized public Arizona Spanish/gold context GeoJSON and KMZ layers."""

from __future__ import annotations

import html
import json
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"

BUILD_DATE = "2026-05-04"


LEGAL_CAUTION = (
    "General historical/mineral screening only. Not a claimability, access, "
    "ownership, safety, archaeological-site, or treasure-cache determination. "
    "Check BLM/Arizona claim records, land status, closures, permits, and local rules before field work."
)

SENSITIVITY_NOTE = (
    "Mapped as a public generalized district, settlement, mission, crossing, or corridor point. "
    "Coordinates are not exact mine workings or confidential archaeological locations."
)

SPANISH_COLONIAL_CONTEXT = [
    {
        "name": "Santa Cruz River - Sonoita Creek Spanish Prospecting Corridor",
        "lon": -110.95,
        "lat": 31.62,
        "county": "Santa Cruz / Pima",
        "location_type": "generalized colonial prospecting corridor",
        "gold_relevance": "AZGS notes late-1600s Spanish prospecting in mountains bordering the Santa Cruz River and Sonoita Creek, with emphasis on metallic deposits.",
        "confidence": "source-supported corridor, generalized",
        "source": "Arizona Geological Survey - Arizona Mineral Resources",
        "source_url": "https://azgs.arizona.edu/mapping-minerals/arizona-mineral-resources",
    },
    {
        "name": "Tumacacori - Tubac Mission/Presidio Corridor",
        "lon": -111.049,
        "lat": 31.590,
        "county": "Santa Cruz",
        "location_type": "public Spanish colonial corridor",
        "gold_relevance": "Public mission/presidio corridor near the Santa Cruz/Sonoita mining-history area; included for Spanish colonial context rather than as a mine coordinate.",
        "confidence": "verified public heritage locations, generalized",
        "source": "NPS Tumacacori and Arizona State Parks Tubac public sites",
        "source_url": "https://www.nps.gov/tuma/",
    },
    {
        "name": "San Xavier del Bac - Tucson Presidio Corridor",
        "lon": -110.991,
        "lat": 32.165,
        "county": "Pima",
        "location_type": "public Spanish colonial corridor",
        "gold_relevance": "Public Spanish colonial mission/presidio context on the Santa Cruz travel corridor; not mapped as a mine or cache.",
        "confidence": "verified public heritage locations, generalized",
        "source": "Mission San Xavier del Bac and Tucson Presidio public sites",
        "source_url": "https://sanxaviermission.org/",
    },
    {
        "name": "Jerome / Verde Mining District Context",
        "lon": -112.113,
        "lat": 34.749,
        "county": "Yavapai",
        "location_type": "historic mining-district context point",
        "gold_relevance": "AZGS notes Antonio de Espejo's 1583 silver discovery south of the San Francisco Peaks, near what some believe is present-day Jerome.",
        "confidence": "historical attribution is qualified by source",
        "source": "Arizona Geological Survey - Arizona Mineral Resources",
        "source_url": "https://azgs.arizona.edu/mapping-minerals/arizona-mineral-resources",
    },
]


PUBLIC_GOLD_DISTRICTS = [
    {
        "name": "Oro Blanco / Arivaca District",
        "lon": -111.37,
        "lat": 31.55,
        "county": "Santa Cruz / Pima",
        "location_type": "generalized gold district",
        "gold_relevance": "Southern Arizona gold district near the Spanish colonial Santa Cruz/Sonoita sphere.",
        "confidence": "public district centroid, generalized",
        "source": "USGS MRDS and USGS Placer Gold Deposits of Arizona context",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Greaterville District",
        "lon": -110.75,
        "lat": 31.78,
        "county": "Pima",
        "location_type": "generalized placer/lode gold district",
        "gold_relevance": "Historically important Santa Rita Mountains gold district; included as a public district-scale point.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Quijotoa District",
        "lon": -112.23,
        "lat": 31.98,
        "county": "Pima",
        "location_type": "generalized gold district",
        "gold_relevance": "Southern Arizona historic gold district; district-level screening point only.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Las Guijas District",
        "lon": -111.53,
        "lat": 31.83,
        "county": "Pima",
        "location_type": "generalized placer gold district",
        "gold_relevance": "Historic southern Arizona placer district; included because it lies in the broader Spanish colonial southern-Arizona region.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "La Paz / Plomosa District",
        "lon": -114.33,
        "lat": 33.65,
        "county": "La Paz",
        "location_type": "generalized placer gold district",
        "gold_relevance": "Major Colorado River-area placer gold district; later than Spanish colonial mining, but a verified Arizona gold locality.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Gila City / Dome District",
        "lon": -114.38,
        "lat": 32.74,
        "county": "Yuma",
        "location_type": "generalized placer gold district",
        "gold_relevance": "Historic lower Colorado/Gila River placer district; public district-scale point.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Weaver / Rich Hill District",
        "lon": -112.69,
        "lat": 34.17,
        "county": "Yavapai",
        "location_type": "generalized placer/lode gold district",
        "gold_relevance": "Central Arizona gold district, mapped at district scale only.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Vulture / Wickenburg District",
        "lon": -112.83,
        "lat": 33.82,
        "county": "Maricopa",
        "location_type": "generalized lode/placer gold district",
        "gold_relevance": "Historic Wickenburg-area gold district, included as a verified Arizona gold locality.",
        "confidence": "public district centroid, generalized",
        "source": "USGS MRDS and Arizona Geological Survey mineral resources context",
        "source_url": "https://azgs.arizona.edu/mapping-minerals/arizona-mineral-resources",
    },
    {
        "name": "Bradshaw Mountains / Lynx Creek District",
        "lon": -112.42,
        "lat": 34.52,
        "county": "Yavapai",
        "location_type": "generalized placer/lode gold district",
        "gold_relevance": "Historic central Arizona placer and lode gold area; public district-scale point.",
        "confidence": "public district centroid, generalized",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
    {
        "name": "Oatman / San Francisco District",
        "lon": -114.38,
        "lat": 35.03,
        "county": "Mohave",
        "location_type": "generalized lode gold district",
        "gold_relevance": "Major historic Arizona lode gold district; not Spanish colonial, but verified gold-mining context.",
        "confidence": "public district centroid, generalized",
        "source": "USGS MRDS and Arizona Geological Survey mineral resources context",
        "source_url": "https://azgs.arizona.edu/mapping-minerals/arizona-mineral-resources",
    },
    {
        "name": "Gold Basin - Lost Basin Districts",
        "lon": -114.18,
        "lat": 35.92,
        "county": "Mohave",
        "location_type": "generalized lode/placer gold districts",
        "gold_relevance": "USGS describes adjacent Gold Basin and Lost Basin districts with recorded gold production and placer/lode sources.",
        "confidence": "USGS district report, generalized",
        "source": "USGS OFR 82-1052",
        "source_url": "https://www.usgs.gov/publications/preliminary-report-geology-and-gold-mineralization-gold-basin-lost-basin-mining",
    },
    {
        "name": "Castle Dome / Kofa Region",
        "lon": -114.14,
        "lat": 33.20,
        "county": "Yuma",
        "location_type": "generalized historic mining region",
        "gold_relevance": "Historic southwestern Arizona precious-metal region; public generalized context point.",
        "confidence": "public district centroid, generalized",
        "source": "USGS MRDS and USGS Placer Gold Deposits of Arizona context",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
]


GENERALIZED_CORRIDORS = [
    {
        "name": "Santa Cruz - Sonoita Spanish Prospecting Corridor",
        "coordinates": [
            [-111.05, 31.46],
            [-111.05, 31.61],
            [-110.97, 31.78],
            [-110.75, 31.78],
        ],
        "location_type": "generalized corridor line",
        "gold_relevance": "Generalized line connecting public Spanish colonial sites with the Santa Cruz/Sonoita mining-history corridor described by AZGS.",
        "confidence": "generalized interpretive corridor",
        "source": "Arizona Geological Survey - Arizona Mineral Resources",
        "source_url": "https://azgs.arizona.edu/mapping-minerals/arizona-mineral-resources",
    },
    {
        "name": "Lower Colorado - Gila Placer District Corridor",
        "coordinates": [
            [-114.62, 32.72],
            [-114.38, 32.74],
            [-114.33, 33.65],
        ],
        "location_type": "generalized corridor line",
        "gold_relevance": "Generalized public corridor tying lower Colorado/Gila placer districts and crossing context.",
        "confidence": "generalized interpretive corridor",
        "source": "USGS Placer Gold Deposits of Arizona",
        "source_url": "https://www.usgs.gov/publications/placer-gold-deposits-arizona",
    },
]


def feature_from_point(record: dict[str, Any], layer: str) -> dict[str, Any]:
    props = {key: value for key, value in record.items() if key not in {"lon", "lat"}}
    props["layer"] = layer
    props["build_date"] = BUILD_DATE
    props["sensitivity_note"] = SENSITIVITY_NOTE
    props["legal_caution"] = LEGAL_CAUTION
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [record["lon"], record["lat"]]},
        "properties": props,
    }


def feature_from_line(record: dict[str, Any], layer: str) -> dict[str, Any]:
    props = {key: value for key, value in record.items() if key != "coordinates"}
    props["layer"] = layer
    props["build_date"] = BUILD_DATE
    props["sensitivity_note"] = SENSITIVITY_NOTE
    props["legal_caution"] = LEGAL_CAUTION
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": record["coordinates"]},
        "properties": props,
    }


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "generated": BUILD_DATE, "features": features}


def write_geojson(name: str, data: dict[str, Any]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def coordinates_text(coords: Iterable[list[float]]) -> str:
    return " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat, *_ in coords)


def placemark_for_feature(feature: dict[str, Any]) -> str:
    props = feature.get("properties") or {}
    name = str(props.get("name") or props.get("layer") or "Feature")
    description = "<br/>".join(
        f"<b>{html.escape(str(key))}</b>: {html.escape(str(value))}"
        for key, value in sorted(props.items())
        if value not in (None, "")
    )
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
    with zipfile.ZipFile(kmz_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml)
    return kmz_path


def main() -> None:
    colonial_context = feature_collection(
        [feature_from_point(record, "Spanish colonial gold context") for record in SPANISH_COLONIAL_CONTEXT]
    )
    gold_districts = feature_collection(
        [feature_from_point(record, "Arizona public gold districts") for record in PUBLIC_GOLD_DISTRICTS]
    )
    corridors = feature_collection(
        [feature_from_line(record, "Generalized Spanish/gold corridors") for record in GENERALIZED_CORRIDORS]
    )
    layers = [
        ("Spanish Colonial Gold Context", colonial_context),
        ("Arizona Public Gold Districts", gold_districts),
        ("Generalized Spanish/Gold Corridors", corridors),
    ]
    bundle = feature_collection([feature for _, layer in layers for feature in layer["features"]])

    paths = [
        write_geojson("az_spanish_gold_context.geojson", colonial_context),
        write_geojson("az_public_gold_districts_generalized.geojson", gold_districts),
        write_geojson("az_spanish_gold_corridors_generalized.geojson", corridors),
        write_geojson("az_spanish_gold_locations_bundle.geojson", bundle),
        write_kmz("az_spanish_gold_locations_bundle.kmz", layers),
        write_kmz("az_spanish_gold_context.kmz", [layers[0]]),
        write_kmz("az_public_gold_districts_generalized.kmz", [layers[1]]),
    ]

    summary = {
        "generated": BUILD_DATE,
        "feature_counts": {folder: len(layer["features"]) for folder, layer in layers},
        "outputs": [str(path.relative_to(HERE)) for path in paths],
        "notes": [
            "Generalized public district/corridor points only.",
            "Not exact dig, treasure, cache, claim, mine-working, or archaeological-site coordinates.",
            "Source URLs are embedded in feature properties.",
        ],
    }
    write_geojson("az_spanish_gold_locations_build_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
