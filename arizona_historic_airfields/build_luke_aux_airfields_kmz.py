#!/usr/bin/env python3
"""Build a KMZ/GeoJSON package for historic Luke auxiliary airfields in Arizona."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_OUTDIR = Path("/mnt/c/Users/Cobiwan Kenobi/Desktop/qgis layers/luke_aux_airfields")

FIELDS = [
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #1 - Wittmann Field",
        "lat": 33.713203,
        "lon": -112.526093,
        "status": "Closed / historic",
        "municipality": "Wittmann / Glendale area",
        "source": "Airfields-Freeman; OurAirports US-1807",
        "notes": "Originally Luke Satellite Field #3, then Luke Auxiliary Field #1. WWII Luke AAF training satellite with four paved runways.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #2 - Beardsley Field",
        "lat": 33.704492,
        "lon": -112.417173,
        "status": "Closed / historic",
        "municipality": "Surprise / Beardsley area",
        "source": "Airfields-Freeman; OurAirports US-1808",
        "notes": "WWII Luke auxiliary field with four bituminous runways. Much of the site has been redeveloped.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #3 - Fighter Field",
        "lat": 33.631276,
        "lon": -112.366533,
        "status": "Closed / historic",
        "municipality": "Surprise / north of Luke AFB",
        "source": "Airfields-Freeman; OurAirports US-1809",
        "notes": "Originally Luke Satellite Field #1, later Luke Auxiliary Field #3. Known as Fighter Field; used for Luke fighter-pilot training.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #4 - Wickenburg Field",
        "lat": 33.745184,
        "lon": -112.633553,
        "status": "Closed / historic",
        "municipality": "Wittmann / Wickenburg area",
        "source": "Airfields-Freeman; OurAirports US-1810",
        "notes": "WWII Luke auxiliary field with three 4,000-foot bituminous runways arranged in a triangle.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #5 - Buckeye Field / Buckeye Municipal Airport",
        "lat": 33.420417,
        "lon": -112.686180,
        "status": "Active civil airport with historic Luke Aux #5 association",
        "municipality": "Buckeye",
        "source": "Mapcarta/OSM/Wikidata; USAAF accident references to Luke Aux Field #5, Buckeye",
        "notes": "Historic Luke Auxiliary Field #5 association; modern site is Buckeye Municipal Airport.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Airfield #6 - Goodyear Field / Perryville area",
        "lat": 33.442972,
        "lon": -112.514162,
        "status": "Closed / historic",
        "municipality": "Buckeye / Goodyear area",
        "source": "Airfields-Freeman; OurAirports US-1367; FAA surplus-property notice",
        "notes": "Built in 1943 as a Luke satellite airfield. Also called Goodyear Field.",
    },
    {
        "folder": "WWII Luke satellite and auxiliary fields",
        "name": "Luke Auxiliary Army Airfield #7 - Hassayampa Field",
        "lat": 33.366234,
        "lon": -112.758179,
        "status": "Closed / historic",
        "municipality": "Buckeye / Hassayampa area",
        "source": "Airfields-Freeman; OurAirports US-1366",
        "notes": "WWII Luke Field Auxiliary #7 with two 4,000-foot bituminous runways; later declared excess.",
    },
    {
        "folder": "Gila Bend and Goldwater Range Luke auxiliary fields",
        "name": "Luke Air Force Auxiliary Field 7 - Ajo area",
        "lat": 32.528254,
        "lon": -112.932801,
        "status": "Closed / historic range auxiliary field",
        "municipality": "Ajo",
        "source": "OurAirports US-1336",
        "notes": "Later Luke-numbered auxiliary field in the Ajo / Goldwater Range area; distinct from WWII Hassayampa Field.",
    },
    {
        "folder": "Gila Bend and Goldwater Range Luke auxiliary fields",
        "name": "Luke Air Force Auxiliary Field 8",
        "lat": 32.605544,
        "lon": -112.878342,
        "status": "Closed / historic range auxiliary field",
        "municipality": "Gila Bend",
        "source": "OurAirports US-1343; DoD/FUDS index references Luke Air Force Aux Field 8",
        "notes": "Closed Luke Air Force auxiliary field south of Gila Bend in the Goldwater Range region.",
    },
    {
        "folder": "Gila Bend and Goldwater Range Luke auxiliary fields",
        "name": "Luke Air Force Auxiliary Field 9",
        "lat": 32.660332,
        "lon": -112.870874,
        "status": "Closed / historic range auxiliary field",
        "municipality": "Gila Bend",
        "source": "OurAirports US-1342",
        "notes": "Closed Luke Air Force auxiliary field in the Gila Bend / Goldwater Range area.",
    },
    {
        "folder": "Gila Bend and Goldwater Range Luke auxiliary fields",
        "name": "Luke Air Force Auxiliary Field 10",
        "lat": 32.719349,
        "lon": -112.852936,
        "status": "Closed / historic range auxiliary field",
        "municipality": "Gila Bend",
        "source": "OurAirports US-1341",
        "notes": "Closed Luke Air Force auxiliary field in the Gila Bend / Goldwater Range area.",
    },
    {
        "folder": "Gila Bend and Goldwater Range Luke auxiliary fields",
        "name": "Luke Air Force Auxiliary Field 11",
        "lat": 32.817395,
        "lon": -112.915120,
        "status": "Closed / historic range auxiliary field",
        "municipality": "Gila Bend",
        "source": "OurAirports US-1340",
        "notes": "Closed Luke Air Force auxiliary field in the Gila Bend / Goldwater Range area.",
    },
    {
        "folder": "Reference - active Luke support field",
        "name": "Gila Bend Air Force Auxiliary Field",
        "lat": 32.887501,
        "lon": -112.720001,
        "status": "Active USAF auxiliary field",
        "municipality": "Gila Bend",
        "source": "Luke AFB 56th Range Management Office; OurAirports KGBN",
        "notes": "Active geographically separated unit supporting Luke AFB and Barry M. Goldwater Range operations. Included as context.",
    },
]


def style_for(folder: str) -> str:
    if folder.startswith("WWII"):
        return "wwii"
    if folder.startswith("Reference"):
        return "active"
    return "range"


def placemark(field: dict) -> str:
    values = [
        ("Status", field["status"]),
        ("Municipality", field["municipality"]),
        ("Latitude", field["lat"]),
        ("Longitude", field["lon"]),
        ("Source", field["source"]),
        ("Notes", field["notes"]),
    ]
    desc = "".join(
        f'<tr><th align="left">{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>'
        for k, v in values
    )
    return f"""<Placemark>
<name>{html.escape(field["name"])}</name>
<styleUrl>#{style_for(field["folder"])}</styleUrl>
<description><![CDATA[<table>{desc}</table>]]></description>
<Point><coordinates>{field["lon"]},{field["lat"]},0</coordinates></Point>
</Placemark>"""


def build_kml(fields: list[dict]) -> str:
    styles = """
<Style id="wwii"><IconStyle><color>ff00a5ff</color><scale>1.15</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="range"><IconStyle><color>ff00ffff</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
<Style id="active"><IconStyle><color>ff00ff00</color><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/airports.png</href></Icon></IconStyle></Style>
"""
    folders = []
    for folder in dict.fromkeys(field["folder"] for field in fields):
        pms = "\n".join(placemark(field) for field in fields if field["folder"] == folder)
        folders.append(f"<Folder><name>{html.escape(folder)}</name>\n{pms}\n</Folder>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Historic Luke Auxiliary Airfields - Arizona</name>
<description><![CDATA[Historic/screening map of Luke auxiliary airfields in Arizona. WWII west-valley fields and later Gila Bend/Goldwater Range Luke-numbered auxiliary fields are separated into folders. Coordinates are screening-grade centroids.]]></description>
{styles}
{"".join(folders)}
</Document>
</kml>
"""


def write_outputs(outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    kml = build_kml(FIELDS)
    kml_path = outdir / "historic_luke_aux_airfields_arizona.kml"
    kmz_path = outdir / "historic_luke_aux_airfields_arizona.kmz"
    geojson_path = outdir / "historic_luke_aux_airfields_arizona.geojson"
    kml_path.write_text(kml, encoding="utf-8")
    with ZipFile(kmz_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [field["lon"], field["lat"]]},
                "properties": {k: v for k, v in field.items() if k not in ("lat", "lon")},
            }
            for field in FIELDS
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
    print(f"placemarks={len(FIELDS)}")


if __name__ == "__main__":
    main()
