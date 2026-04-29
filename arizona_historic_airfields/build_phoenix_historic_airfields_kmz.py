#!/usr/bin/env python3
"""Build a KMZ/GeoJSON package for closed historic airfields around Greater Phoenix."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_OUTDIR = Path("/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/phoenix_historic_airfields")

SOURCES = {
    "NW": "https://www.airfieldsfreeman.com/AZ/Airfields_AZ_Phoenix_NW.htm",
    "NE": "https://www.airfieldsfreeman.com/AZ/Airfields_AZ_Phoenix_NE.htm",
    "SE": "https://www.airfieldsfreeman.com/AZ/Airfields_AZ_Phoenix_SE.htm",
    "SW": "https://www.airfieldsfreeman.com/AZ/Airfields_AZ_Phoenix_SW.htm",
    "BONEYARD": "AirplaneBoneyards; HomeTownLocator; Wikimedia 1950 NAF Litchfield Park aerial photo metadata; Avgeekery NAS Litchfield Park history",
}

FIELDS = [
    ("Northwest Phoenix", "Coyner Airfield (AZ60)", 33.507, -112.475, "Litchfield Park", "Closed; no trace by 2024", "Private rural airfield active into the 2010s; closed during residential development.", SOURCES["NW"]),
    ("Northwest Phoenix", "Pleasant Valley Airport (P48)", 33.801, -112.249, "Peoria", "Closed / redeveloped", "Former private glider and general aviation field northwest of Phoenix.", SOURCES["NW"]),
    ("Northwest Phoenix", "McGill Ultralight Field", 33.683283, -112.165883, "Glendale", "Closed / historic ultralight field", "Small ultralight airfield listed in Phoenix northwest abandoned-airfield records.", SOURCES["NW"]),
    ("Northwest Phoenix", "Original Airhaven Airport", 33.49, -112.12, "Alhambra / Phoenix", "Closed / historic", "Early Airhaven site in the Alhambra area, separate from later Glendale/Peoria Air Haven.", SOURCES["NW"]),
    ("Northwest Phoenix", "Air Haven Airport / original Glendale Municipal Airport", 33.57064, -112.22858, "Peoria / Glendale", "Closed / historic", "Former Air Haven / original Glendale Municipal field.", SOURCES["NW"]),
    ("Northwest Phoenix", "Thunderbird Field #1", 33.620132, -112.179959, "Glendale", "Closed / redeveloped", "WWII contract training field later reused as the Thunderbird school campus area.", SOURCES["NW"]),
    ("Northwest Phoenix", "Thunderbird #1 Auxiliary Airfield A-1", 33.643634, -112.095823, "Phoenix", "Closed / historic", "Auxiliary field associated with Thunderbird Field #1 training operations.", SOURCES["NW"]),
    ("Northwest Phoenix", "Thunderbird #1 Auxiliary Airfield A-2", 33.656211, -112.24225, "Peoria", "Closed / historic", "Auxiliary field associated with Thunderbird Field #1 training operations.", SOURCES["NW"]),
    ("Northwest Phoenix", "Pylant Airport / Thunderbird #1 Aux AAF A-3 / Paradise Airport", 33.58066, -112.1034, "Phoenix", "Closed / historic", "Civil field with Thunderbird auxiliary-field history.", SOURCES["NW"]),
    ("Northwest Phoenix", "Sun City Airfield", 33.740008, -112.259846, "Sun City", "Closed / historic", "Former airfield in the Sun City area.", SOURCES["NW"]),
    ("Northwest Phoenix", "Turf Paradise Airfield", 33.63252, -112.09212, "Phoenix", "Closed / historic", "Former field near Turf Paradise in north Phoenix.", SOURCES["NW"]),
    ("Northwest Phoenix", "Williams Field / Rex Williams Field / Moseley Field", 33.50331, -112.25281, "Phoenix", "Closed / historic", "Former west Phoenix airfield known under several names.", SOURCES["NW"]),
    ("Northwest Phoenix", "Fram Field", 33.52951, -112.27693, "Glendale", "Closed / farmed over", "Small private field northwest of 99th Avenue and Rose Lane area.", SOURCES["NW"]),
    ("Northeast Phoenix", "Sky-Hi Pioneer Airport", 33.673, -112.001, "Phoenix", "Closed / no trace", "Former private skydiving airfield, closed between 1985 and 1993.", SOURCES["NE"]),
    ("Northeast Phoenix", "Motorola Airfield", 33.46, -111.9, "Scottsdale", "Closed / removed", "Former private/industrial flight-test strip at the Motorola facility.", SOURCES["NE"]),
    ("Northeast Phoenix", "Casa Blanca Airport", 33.52, -111.93, "Scottsdale", "Closed / redeveloped", "Former resort airstrip associated with the Casa Blanca Inn.", SOURCES["NE"]),
    ("Northeast Phoenix", "North Phoenix Airport / Cactus Development Inc. Airport", 33.6, -112.03, "Phoenix / Cactus", "Closed / redeveloped", "Former auxiliary/commercial field with two dirt-oiled runways.", SOURCES["NE"]),
    ("Southwest Phoenix", "International Harvester Proving Ground Airfield", 33.3, -112.054, "Phoenix / Ahwatukee area", "Closed / redeveloped", "Private proving-ground airstrip depicted on 1950s/1960s maps.", SOURCES["SW"]),
    ("Southwest Phoenix", "Air-Topia Airport", 33.4, -112.16, "Phoenix", "Closed / mostly redeveloped", "WWII-era auxiliary/crop-dusting field in southwest Phoenix.", SOURCES["SW"]),
    ("Southwest Phoenix", "South Phoenix Airport", 33.4134, -112.05089, "Phoenix", "Closed / historic", "Former south Phoenix airfield near the 23rd Street / Southern Avenue area.", SOURCES["SW"]),
    ("Southwest Phoenix", "Litchfield Park Airport", 33.50185, -112.37484, "Litchfield Park", "Closed / historic", "Former civil airport close to Luke AFB; closed by 1969 charting.", SOURCES["SW"]),
    ("Southeast Phoenix and East Valley", "Oasis Airport", 33.414, -111.64, "Mesa", "Closed / freeway redevelopment", "Small general aviation field depicted from 1947 into the 1960s.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Mesa Airport", 33.43773, -111.84325, "Mesa", "Closed / historic", "Former City of Mesa public-use/crop-dusting field.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Mesa Air Park", 33.41963, -111.86099, "Mesa", "Closed / historic", "Separate from Mesa Airport; former east valley airfield.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Tempe Airport", 33.40428, -111.95206, "Tempe", "Closed / redeveloped", "Former Tempe field south of Broadway Road near the railroad tracks.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Gilbert Airport", 33.34486, -111.79454, "Gilbert", "Closed / redeveloped", "Former Gilbert civil airfield.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Gilbert Auxiliary Army Airfield #1", 33.38732, -111.67149, "Mesa / Buckhorn", "Closed / redeveloped", "Former Williams Field auxiliary airfield.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Goodyear AF Auxiliary / Chandler Memorial / Gila River Memorial Airport", 33.243401, -111.913002, "Chandler", "Closed / derelict historic field", "Former Williams auxiliary and later Goodyear/Chandler Memorial/Gila River Memorial site.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Rittenhouse Auxiliary AAF #2 / Rittenhouse Field", 33.255, -111.523, "Queen Creek", "Historic military auxiliary; currently Army heliport context", "Former Williams Field Auxiliary #2; included for historic-airfield context.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Queen Creek Airfield", 33.256, -111.631, "Queen Creek", "Closed / historic", "Former small airfield in the Queen Creek area.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Florence Junction Airport - first location", 33.254623, -111.346521, "Florence Junction", "Closed / historic", "First known Florence Junction airport location.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Florence Junction Airport - second location", 33.259486, -111.329055, "Apache Junction / Florence Junction", "Closed / historic", "Second Florence Junction airport location.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Francisco Grande Airfield", 32.883948, -111.8573, "Casa Grande", "Closed / historic", "Former airfield associated with the Francisco Grande area.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Three Point Airport (E58)", 32.901101, -111.761255, "Casa Grande", "Closed / historic", "Former Casa Grande-area airfield.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Coolidge Airpark", 32.954, -111.518, "Coolidge", "Closed / redeveloped", "Former Coolidge-area airpark with no trace remaining by recent imagery.", SOURCES["SE"]),
    ("Southeast Phoenix and East Valley", "Coolidge Flying Field / original Coolidge Airport", 32.97171, -111.54681, "Coolidge", "Closed / historic", "Original Coolidge airport/flying-field location.", SOURCES["SE"]),
    ("Aircraft boneyards and storage", "NAF/NAS Litchfield Park Navy aircraft boneyard - Phoenix Goodyear Airport", 33.4258333, -112.3722222, "Goodyear / Litchfield Park area", "Historic Navy aircraft storage boneyard; current airport/storage/maintenance facility", "World War II Naval Air Facility Litchfield Park, later NAS Litchfield Park. After WWII it became a major Navy/Marine/Coast Guard aircraft storage and preservation site before military storage was consolidated at Davis-Monthan. The plotted point is the historical facility centroid/current Phoenix Goodyear Airport area, not a public-access point.", SOURCES["BONEYARD"]),
]


def normalized_fields() -> list[dict]:
    seen = set()
    rows = []
    for folder, name, lat, lon, municipality, status, notes, source in FIELDS:
        if name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "folder": folder,
                "name": name,
                "lat": lat,
                "lon": lon,
                "municipality": municipality,
                "status": status,
                "notes": notes,
                "source": source,
            }
        )
    return rows


def style_for(folder: str) -> str:
    if folder.startswith("Northwest"):
        return "nw"
    if folder.startswith("Northeast"):
        return "ne"
    if folder.startswith("Southwest"):
        return "sw"
    if folder.startswith("Aircraft"):
        return "boneyard"
    return "se"


def placemark(row: dict) -> str:
    values = [
        ("Status", row["status"]),
        ("Area", row["folder"]),
        ("Municipality", row["municipality"]),
        ("Latitude", row["lat"]),
        ("Longitude", row["lon"]),
        ("Notes", row["notes"]),
        ("Source", row["source"]),
    ]
    desc = "".join(
        f'<tr><th align="left">{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>'
        for k, v in values
    )
    return f"""<Placemark>
<name>{html.escape(row["name"])}</name>
<styleUrl>#{style_for(row["folder"])}</styleUrl>
<description><![CDATA[<table>{desc}</table>]]></description>
<Point><coordinates>{row["lon"]},{row["lat"]},0</coordinates></Point>
</Placemark>"""


def build_kml(rows: list[dict]) -> str:
    styles = """
<Style id="nw"><IconStyle><color>ffff9900</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="ne"><IconStyle><color>ff00aa55</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="sw"><IconStyle><color>ffcc33ff</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="se"><IconStyle><color>ff0066ff</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="boneyard"><IconStyle><color>ff0000ff</color><scale>1.25</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
"""
    order = [
        "Northwest Phoenix",
        "Northeast Phoenix",
        "Southwest Phoenix",
        "Southeast Phoenix and East Valley",
        "Aircraft boneyards and storage",
    ]
    folders = []
    for folder in order:
        folder_rows = [row for row in rows if row["folder"] == folder]
        if not folder_rows:
            continue
        pms = "\n".join(placemark(row) for row in folder_rows)
        folders.append(f"<Folder><name>{html.escape(folder)}</name>\n{pms}\n</Folder>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Closed and Abandoned Historic Airfields - Greater Phoenix Area</name>
<description><![CDATA[Closed, abandoned, historically displaced airfields, and a marked historic aircraft boneyard/storage location around the Phoenix metro and nearby east/west valley exurbs. Luke auxiliary fields are intentionally excluded because they are in the separate Luke auxiliary KMZ. Coordinates are screening-grade centroids.]]></description>
{styles}
{"".join(folders)}
</Document>
</kml>
"""


def write_outputs(outdir: Path) -> dict[str, Path]:
    rows = normalized_fields()
    outdir.mkdir(parents=True, exist_ok=True)
    kml = build_kml(rows)
    kml_path = outdir / "closed_abandoned_historic_airfields_greater_phoenix.kml"
    kmz_path = outdir / "closed_abandoned_historic_airfields_greater_phoenix.kmz"
    geojson_path = outdir / "closed_abandoned_historic_airfields_greater_phoenix.geojson"
    kml_path.write_text(kml, encoding="utf-8")
    with ZipFile(kmz_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": {k: v for k, v in row.items() if k not in ("lon", "lat")},
            }
            for row in rows
        ],
    }
    geojson_path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    return {"kml": kml_path, "kmz": kmz_path, "geojson": geojson_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()
    outputs = write_outputs(args.outdir)
    for path in outputs.values():
        print(path)
    print(f"placemarks={len(normalized_fields())}")


if __name__ == "__main__":
    main()
