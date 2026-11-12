"""Finds what must never be published: a CQC location or provider ID, the name of a sampled
service, or a run of words from a cached report (threat model T7).

Report text is public on CQC's website, so one exact sentence finds its report by search, and
the provider with it. A run of RUN_WORDS words is long enough to single out a report. A run found
in the reports of STOCK_PROVIDERS or more providers is CQC's own stock wording (its templates),
which singles out no one, so it is allowed: the rule is about how widely the words are shared,
never about which words they are.

`findings` is pure. `load_oracle` reads the private files in `data/` (git-ignored), so only the
owner's machine runs the scan against the real reports.
"""

import csv
import json
import re
from pathlib import Path
from typing import Any

RUN_WORDS = 8
STOCK_PROVIDERS = 5
# CQC location and provider IDs: "1-" and digits. Any ID in that form counts, sampled or not.
CQC_ID = re.compile(r"(?<![\w-])1-\d{6,}(?!\w)")
NAME_COLUMNS = ("Name", "Also known as", "Provider name")
LOCATION_COLUMN = "CQC Location ID (for office use only)"


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def runs(text: str) -> set[str]:
    """Every run of RUN_WORDS consecutive words, ignoring case and punctuation."""
    found = words(text)
    return {" ".join(found[i : i + RUN_WORDS]) for i in range(len(found) - RUN_WORDS + 1)}


def private_runs(reports: list[tuple[str, str]]) -> set[str]:
    """The runs in (provider, text) pairs, less the stock wording shared by STOCK_PROVIDERS or
    more providers."""
    providers: dict[str, set[str]] = {}
    for provider, text in reports:
        for run in runs(text):
            providers.setdefault(run, set()).add(provider)
    return {run for run, seen in providers.items() if len(seen) < STOCK_PROVIDERS}


def findings(texts: dict[str, str], names: list[str], secret_runs: set[str]) -> list[str]:
    """Every leak in the texts (path -> text), as "path: what". Names are matched as written,
    as whole words: they are proper nouns, and some are also ordinary words in lower case."""
    patterns = [re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)") for name in names]
    found = []
    for path, text in texts.items():
        for match in CQC_ID.finditer(text):
            found.append(f"{path}: a CQC ID ({match.group(0)})")
        for pattern in patterns:
            if pattern.search(text):
                # The name itself is not printed, so this output can be shared.
                found.append(f"{path}: the name of a sampled service")
        hits = sorted(runs(text) & secret_runs)
        if hits:
            first = " ".join(hits[0].split()[:4])
            found.append(f"{path}: {len(hits)} runs of words from a report (one starts: {first})")
    return found


def load_oracle(data: Path) -> tuple[list[str], set[str]]:
    """The sampled services' names, from CQC's directory file, and the private runs of every
    cached report (its overview and its sections)."""
    sampled = {record["location"] for record in read_json(data / "sample.json")}
    names: set[str] = set()
    for row in directory_rows(data / "raw" / "directory"):
        if row[LOCATION_COLUMN] in sampled:
            names.update(row[column].strip() for column in NAME_COLUMNS if row[column].strip())
    reports = []
    for path in sorted((data / "reports").glob("*/*.json")):
        report = read_json(path)
        lines = report["overview"] + [p for s in report["sections"] for p in s["paragraphs"]]
        reports.append((report["provider"], "\n".join(lines)))
    return sorted(names), private_runs(reports)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def directory_rows(folder: Path) -> list[dict[str, str]]:
    """The rows of the one directory CSV in the folder, by column name. The file opens with four
    lines of title before its header."""
    (path,) = sorted(folder.glob("*.csv"))
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    header = rows[4]
    return [dict(zip(header, row, strict=False)) for row in rows[5:]]
