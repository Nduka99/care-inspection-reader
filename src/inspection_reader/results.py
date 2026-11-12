"""The public results file, `site/results.json`: aggregates only, every number rebuilt from the
private runs.

- `build` turns the registered reports and the runs into plain data.
- `problems` holds the file to SCHEMA, an allow-list of every key and its type, so no per-report
  field (a location, a list of sections, a quote) can enter it.
- `differences` compares the committed file with a fresh build, so a hand-edited or stale number
  is caught.
"""

import math
from typing import Any

from inspection_reader import analysis, evaluate
from inspection_reader.extract import STATEMENTS

# Chosen on the dev set by a rule written down before any model ran (see the README); the other
# model is kept so the cost of the choice is measured.
CHOSEN = "qwen3.5-4b"
COMPARED = "gemma-4-e4b"
RATINGS = ("Inadequate", "Requires improvement", "Good", "Outstanding")
SCORES = ("1", "2", "3", "4")
DIGITS = 4
# Counted by hand on 6 Nov 2026 from a seeded sample (seed 2026) of the chosen model's flagged
# sections scored 3 on test. A reading cannot be recomputed; it is copied as recorded.
READ_BY_HAND = {
    "good_flags_sampled": 20,
    "good_flags_real_minor": 13,
    "good_flags_misread": 5,
    "good_flags_out_of_context": 1,
    "good_flags_unclear": 1,
}


def keyed(names: tuple[str, ...], value: object) -> dict[str, object]:
    return {name: value for name in names}


PROPORTION = {"found": int, "total": int, "rate": float, "low": float, "high": float}
INTERVAL = {"value": float, "low": float, "high": float}
SET = {
    "reports": int,
    "sections": int,
    "carried_over_left_out": int,
    "by_score": keyed(SCORES, int),
}
MEASURES = {
    "recall_score_1": PROPORTION,
    "recall_score_2_or_below": PROPORTION,
    "flag_rate_score_3": PROPORTION,
    "flag_rate_score_4": PROPORTION,
    "category_agreement": PROPORTION,
    "quote_drops": PROPORTION,
    "errors": int,
}
SCHEMA = {
    "models": {"chosen": str, "compared": str},
    "sample": {"agencies": keyed(RATINGS, int), "with_scored_text": keyed(RATINGS, int)},
    "sets": {"dev": SET, "test": SET},
    "dev": {"chosen": MEASURES, "compared": MEASURES},
    "test": {"chosen": MEASURES, "compared": MEASURES},
    "paired_test": {
        "shortfalls_caught_by_chosen_only": int,
        "shortfalls_caught_by_compared_only": int,
        "shortfalls_missed_by_both": int,
        "p_exact": float,
    },
    "grading_test": keyed(
        ("auroc_shortfall", "tau_b", "shuffled_auroc_shortfall", "shuffled_tau_b"), INTERVAL
    ),
    "by_statement_test": keyed(
        tuple(STATEMENTS),
        {
            "recall_score_2_or_below": PROPORTION,
            "flag_rate_score_3": PROPORTION,
            "category_agreement": PROPORTION,
        },
    ),
    "read_by_hand": keyed(tuple(READ_BY_HAND), int),
}

Reports = list[dict[str, Any]]
Runs = dict[str, dict[str, Any]]


def rounded(proportion: dict[str, Any]) -> dict[str, Any]:
    found = {}
    for key, value in proportion.items():
        found[key] = round(value, DIGITS) if isinstance(value, float) else value
    return found


def measures(reports: Reports, runs: Runs) -> dict[str, Any]:
    scored = evaluate.score(reports, runs)
    found: dict[str, Any] = {key: rounded(scored[key]) for key in MEASURES if key != "errors"}
    found["errors"] = len(scored["errors"])
    return found


def describe_set(reports: Reports, runs: Runs) -> dict[str, Any]:
    scored = evaluate.score(reports, runs)
    sections = evaluate.scored_sections(reports, runs)
    by_score = {score: sum(1 for s in sections if str(s["score"]) == score) for score in SCORES}
    return {
        "reports": scored["reports"],
        "sections": scored["sections"],
        "carried_over_left_out": scored["not_assessed_left_out"],
        "by_score": by_score,
    }


def sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test (McNemar's exact test on the discordant pairs)."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1))
    return min(1.0, 2 * tail / math.pow(2, n))


def paired(reports: Reports, chosen: Runs, compared: Runs) -> dict[str, Any]:
    """The shortfall sections (scores 1-2) one model caught and the other missed."""
    pairs = zip(
        evaluate.scored_sections(reports, chosen),
        evaluate.scored_sections(reports, compared),
        strict=True,
    )
    chosen_only = 0
    compared_only = 0
    both_missed = 0
    for mine, theirs in pairs:
        if mine["score"] > 2:
            continue
        if mine["findings"] and not theirs["findings"]:
            chosen_only += 1
        elif theirs["findings"] and not mine["findings"]:
            compared_only += 1
        elif not mine["findings"]:
            both_missed += 1
    return {
        "shortfalls_caught_by_chosen_only": chosen_only,
        "shortfalls_caught_by_compared_only": compared_only,
        "shortfalls_missed_by_both": both_missed,
        "p_exact": round(sign_test(chosen_only, compared_only), DIGITS),
    }


def grading(reports: Reports, runs: Runs) -> dict[str, Any]:
    sections = evaluate.scored_sections(reports, runs)
    real = analysis.grading(sections)
    control = analysis.grading(analysis.shuffled(sections))
    found = {}
    for name, result in (("", real), ("shuffled_", control)):
        for measure in ("auroc_shortfall", "tau_b"):
            low, high = result[measure]["interval"]
            found[name + measure] = {
                "value": round(result[measure]["value"], DIGITS),
                "low": round(low, DIGITS),
                "high": round(high, DIGITS),
            }
    return found


def by_statement(reports: Reports, runs: Runs) -> dict[str, Any]:
    topics = analysis.by_topic(evaluate.scored_sections(reports, runs))
    keys = ("recall_score_2_or_below", "flag_rate_score_3", "category_agreement")
    found = {}
    for statement in STATEMENTS:
        found[statement] = {key: rounded(topics[statement][key]) for key in keys}
    return found


def count_by_rating(records: list[dict[str, Any]]) -> dict[str, int]:
    return {rating: sum(1 for r in records if r["rating"] == rating) for rating in RATINGS}


def build(
    sampled: list[dict[str, Any]],
    reports: dict[str, Reports],
    runs: dict[str, dict[str, Runs]],
) -> dict[str, Any]:
    """The public results. `sampled` is the chosen agencies with their Safe rating; `reports`
    maps each split to its registered reports; `runs` maps split, then model, to the runs by
    location."""
    with_text = {r["location"] for split in reports.values() for r in split}
    test = reports["test"]
    return {
        "models": {"chosen": CHOSEN, "compared": COMPARED},
        "sample": {
            "agencies": count_by_rating(sampled),
            "with_scored_text": count_by_rating([r for r in sampled if r["location"] in with_text]),
        },
        "sets": {split: describe_set(reports[split], runs[split][CHOSEN]) for split in reports},
        "dev": {
            "chosen": measures(reports["dev"], runs["dev"][CHOSEN]),
            "compared": measures(reports["dev"], runs["dev"][COMPARED]),
        },
        "test": {
            "chosen": measures(test, runs["test"][CHOSEN]),
            "compared": measures(test, runs["test"][COMPARED]),
        },
        "paired_test": paired(test, runs["test"][CHOSEN], runs["test"][COMPARED]),
        "grading_test": grading(test, runs["test"][CHOSEN]),
        "by_statement_test": by_statement(test, runs["test"][CHOSEN]),
        "read_by_hand": dict(READ_BY_HAND),
    }


def flat(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Every leaf by its path, such as "test/chosen/recall_score_1/found"."""
    found = {}
    for key, value in data.items():
        if isinstance(value, dict):
            found.update(flat(value, f"{prefix}{key}/"))
        else:
            found[f"{prefix}{key}"] = value
    return found


def problems(data: dict[str, Any]) -> list[str]:
    """Every way the file departs from SCHEMA: a key not on the allow-list, a missing key, or a
    value of the wrong type (a list or text where a number belongs)."""
    allowed = flat(SCHEMA)
    present = flat(data)
    found = [f"{path}: not allowed" for path in present if path not in allowed]
    found += [f"{path}: missing" for path in allowed if path not in present]
    for path, value in present.items():
        if path in allowed and type(value) is not allowed[path]:
            found.append(f"{path}: {type(value).__name__}, not {allowed[path].__name__}")
    return found


def differences(committed: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    """Every path whose value in the committed file differs from a fresh build."""
    old = flat(committed)
    new = flat(fresh)
    return [
        f"{path}: {old.get(path)} in the file, {new.get(path)} from the runs"
        for path in sorted(set(old) | set(new))
        if old.get(path) != new.get(path)
    ]
