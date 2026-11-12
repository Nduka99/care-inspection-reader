"""Scores for one run against the inspectors' scores.

The unit is one Safe quality statement in one report. A section is flagged when at least one
verified finding lies inside it. Each measure has a Wilson 95% interval:
- recall at score 1 ("significant shortfalls"), then at score 2 or below: the share flagged;
- flag rate at score 3 ("a good standard") and at score 4 ("exceptional"). Text scored 3 can
  still mention small issues, so this is a flag rate, not a false-positive rate;
- category agreement: of the flagged sections scored 2 or below, the share with a finding
  whose category is the section's own statement;
- quote drops: findings dropped because their quote is not in the text.
A report the model could not answer counts as "no findings", which can only lower recall.
"""

import re
from typing import Any

from inspection_reader.metrics import proportion

# CQC's own wording for a statement it did not assess this time: the score is carried over from
# the previous rating, so it says nothing about the text (only statements with
# their own text are used). Found in the error sample of 2026-11-05: these sections were scored.
NOT_ASSESSED = re.compile(
    r"we did not look at .{0,80}? during this assessment\. the score for this quality statement"
    r" is based on the previous rating",
    re.IGNORECASE,
)


def assessed(section: dict[str, Any]) -> bool:
    """False for a section whose text is CQC's carried-over-score wording."""
    text = " ".join(section.get("paragraphs", [])).strip()
    return NOT_ASSESSED.match(text) is None


def scored_sections(
    reports: list[dict[str, Any]], runs: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every assessed section of every report, with the run's findings that lie inside it.
    Carried-over sections are left out: their score was not given for their text."""
    sections = []
    for report in reports:
        run = runs[report["location"]]
        for index, section in enumerate(report["sections"]):
            if not assessed(section):
                continue
            inside = [f for f in run.get("findings", []) if f["section"] == index]
            sections.append(
                {
                    "location": report["location"],
                    "statement": section["statement"],
                    "score": section["score"],
                    "findings": inside,
                }
            )
    return sections


def flagged(sections: list[dict[str, Any]]) -> dict[str, float | int]:
    return proportion(sum(1 for s in sections if s["findings"]), len(sections))


def score(reports: list[dict[str, Any]], runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sections = scored_sections(reports, runs)
    shortfalls = [s for s in sections if s["score"] <= 2]
    caught = [s for s in shortfalls if s["findings"]]
    agreeing = [s for s in caught if any(f["category"] == s["statement"] for f in s["findings"])]
    kept = sum(len(runs[r["location"]].get("findings", [])) for r in reports)
    dropped = sum(runs[r["location"]].get("dropped", 0) for r in reports)
    missed = [
        {"location": s["location"], "statement": s["statement"]}
        for s in sections
        if s["score"] == 1 and not s["findings"]
    ]
    return {
        "reports": len(reports),
        "sections": len(sections),
        "not_assessed_left_out": sum(
            1 for report in reports for section in report["sections"] if not assessed(section)
        ),
        "recall_score_1": flagged([s for s in sections if s["score"] == 1]),
        "recall_score_2_or_below": flagged(shortfalls),
        "flag_rate_score_3": flagged([s for s in sections if s["score"] == 3]),
        "flag_rate_score_4": flagged([s for s in sections if s["score"] == 4]),
        "category_agreement": proportion(len(agreeing), len(caught)),
        "quote_drops": proportion(dropped, kept + dropped),
        "errors": [r["location"] for r in reports if "error" in runs[r["location"]]],
        "missed_score_1": missed,
    }
