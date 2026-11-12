"""The Safe rating of every home care agency, from two CQC files (Open Government Licence).

- The care directory CSV lists every location with its service types; home care agencies have
  "Homecare agencies" among them.
- The "Latest ratings" spreadsheet (ODS) has one row per location, service and domain. Its
  content.xml unpacks to over 1 GB, so it is read as a stream, one row at a time.
"""

import csv
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from pathlib import Path

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
# A run of identical cells is stored once with a repeat count; trailing empty cells repeat to
# the sheet's last column (16,384), so a run is cut at this many.
MAX_REPEAT = 64
# A location that runs more than one kind of service has no location-level rating under CQC's
# new approach; its home care service is then rated on a row of its own.
GROUPS = ("Overall", "Homecare")
# "Not Rated" and "Insufficient evidence to rate" rows carry no score to compare against.
RATINGS = ("Inadequate", "Requires improvement", "Good", "Outstanding")


def homecare_locations(directory_csv: Path) -> set[str]:
    """The location IDs of every home care agency in the directory."""
    with directory_csv.open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    # The file opens with four lines of title before its header.
    header = rows[4]
    service = header.index("Service types")
    location = header.index("CQC Location ID (for office use only)")
    return {row[location] for row in rows[5:] if "Homecare agencies" in row[service]}


def sheet_rows(ods: Path, sheet: str) -> Iterator[list[str]]:
    """Each row of one sheet, as the text of its cells."""
    with zipfile.ZipFile(ods) as archive, archive.open("content.xml") as content:
        current = ""
        for event, element in ET.iterparse(content, events=("start", "end")):
            if event == "start" and element.tag == TABLE + "table":
                current = element.get(TABLE + "name", "")
            elif event == "end" and element.tag == TABLE + "table-row":
                if current == sheet:
                    yield row_cells(element)
                element.clear()


def row_cells(row: ET.Element) -> list[str]:
    cells = []
    for cell in row.findall(TABLE + "table-cell"):
        repeat = min(int(cell.get(TABLE + "number-columns-repeated", "1")), MAX_REPEAT)
        cells += ["".join(cell.itertext())] * repeat
    return cells


def safe_ratings(ods: Path, homecare: set[str]) -> list[dict[str, str]]:
    """One record per home care agency: its latest Safe rating and when it was published.

    The location-level ("Overall") row is used when there is one; otherwise the row for the
    location's home care service.
    """
    rows = sheet_rows(ods, "Locations")
    header = next(rows)
    column = {name: index for index, name in enumerate(header)}
    found: dict[str, dict[str, str]] = {}
    for cells in rows:
        if len(cells) < len(header) or cells[column["Location ID"]] not in homecare:
            continue
        group = cells[column["Service / Population Group"]]
        if cells[column["Domain"]] != "Safe" or group not in GROUPS:
            continue
        if cells[column["Latest Rating"]] not in RATINGS:
            continue
        location = cells[column["Location ID"]]
        if found.get(location, {}).get("group") == "Overall":
            continue
        day, month, year = cells[column["Publication Date"]].split("/")
        found[location] = {
            "location": location,
            "provider": cells[column["Provider ID"]],
            "group": group,
            "rating": cells[column["Latest Rating"]],
            "published": f"{year}-{month}-{day}",
        }
    return sorted(found.values(), key=lambda record: record["location"])
