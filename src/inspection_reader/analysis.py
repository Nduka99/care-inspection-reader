"""Analyses of a finished run beyond the main measures in `evaluate.py`. Their rules were written
down on 5 Nov 2026, before any of them was computed.

- Grading: does the number of findings in a section follow the inspector's score? AUROC and
  Kendall's tau-b, both computed from a table of (score, findings) counts.
- Intervals: a cluster bootstrap that resamples whole reports, because sections of one report
  are correlated (Pang et al. 2023; Field and Welsh 2007).
- By topic: the main measures for each Safe quality statement.
- Memory check: reports published before and after the model's training cutoff (Roberts et al.,
  ICLR 2024).
"""

import math
import random
from typing import Any

from inspection_reader.evaluate import flagged
from inspection_reader.metrics import proportion

ROUNDS = 2000
SEED = 2026
# Gemma 4's pre-training data has "a cutoff date of January 2025" (its model card).
CUTOFF = "2025-01-31"
SHORTFALL = (1, 2)
GOOD = (3, 4)

Counts = dict[tuple[int, int], int]


def counts(sections: list[dict[str, Any]]) -> Counts:
    """How many sections have each (score, number of findings) pair."""
    found: Counts = {}
    for section in sections:
        key = (section["score"], len(section["findings"]))
        found[key] = found.get(key, 0) + 1
    return found


def merged(tables: list[Counts]) -> Counts:
    total: Counts = {}
    for table in tables:
        for key, count in table.items():
            total[key] = total.get(key, 0) + count
    return total


def auroc(table: Counts, positive: tuple[int, ...], negative: tuple[int, ...]) -> float | None:
    """The chance that a section scored in `positive` has more findings than one scored in
    `negative`, with ties counting half. None when either group is empty."""
    wins = 0.0
    pairs = 0
    for (score_p, found_p), count_p in table.items():
        if score_p not in positive:
            continue
        for (score_n, found_n), count_n in table.items():
            if score_n not in negative:
                continue
            pairs += count_p * count_n
            if found_p > found_n:
                wins += count_p * count_n
            elif found_p == found_n:
                wins += 0.5 * count_p * count_n
    return wins / pairs if pairs else None


def tau_b(table: Counts) -> float | None:
    """Kendall's tau-b between the number of findings and severity (5 minus the score), so a
    positive value means more findings go with worse scores."""
    cells = [(found, 5 - score, count) for (score, found), count in table.items()]
    n = sum(count for _, _, count in cells)
    concordant = 0
    discordant = 0
    for found_a, severity_a, count_a in cells:
        for found_b, severity_b, count_b in cells:
            sign = (found_a - found_b) * (severity_a - severity_b)
            if sign > 0:
                concordant += count_a * count_b
            elif sign < 0:
                discordant += count_a * count_b
    by_found: dict[int, int] = {}
    by_severity: dict[int, int] = {}
    for found, severity, count in cells:
        by_found[found] = by_found.get(found, 0) + count
        by_severity[severity] = by_severity.get(severity, 0) + count
    pairs = n * (n - 1) / 2
    tied_found = sum(c * (c - 1) / 2 for c in by_found.values())
    tied_severity = sum(c * (c - 1) / 2 for c in by_severity.values())
    denominator = math.sqrt((pairs - tied_found) * (pairs - tied_severity))
    # Each unordered pair was counted twice, once in each order.
    return (concordant - discordant) / 2 / denominator if denominator else None


def by_report(sections: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        grouped.setdefault(section["location"], []).append(section)
    return grouped


def interval(values: list[float]) -> tuple[float, float] | None:
    """The 2.5th and 97.5th percentiles, or None when there is nothing to rank."""
    if not values:
        return None
    ordered = sorted(values)
    return (ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))])


def resample(names: list[str], rng: random.Random) -> list[str]:
    """Whole reports drawn with replacement, so each report's sections stay together."""
    return [rng.choice(names) for _ in names]


def grading(
    sections: list[dict[str, Any]], rounds: int = ROUNDS, seed: int = SEED
) -> dict[str, Any]:
    """AUROC (shortfall against Good or Outstanding), AUROC (Good against Outstanding) and
    tau-b, each with a cluster-bootstrap interval."""
    tables = {name: counts(group) for name, group in by_report(sections).items()}
    names = sorted(tables)
    measures = {
        "auroc_shortfall": lambda t: auroc(t, SHORTFALL, GOOD),
        "auroc_good_vs_outstanding": lambda t: auroc(t, (3,), (4,)),
        "tau_b": tau_b,
    }
    whole = merged(list(tables.values()))
    samples: dict[str, list[float]] = {key: [] for key in measures}
    rng = random.Random(seed)
    for _ in range(rounds):
        table = merged([tables[name] for name in resample(names, rng)])
        for key, measure in measures.items():
            value = measure(table)
            if value is not None:
                samples[key].append(value)
    result: dict[str, Any] = {}
    for key, measure in measures.items():
        result[key] = {"value": measure(whole), "interval": interval(samples[key])}
    return result


def shuffled(sections: list[dict[str, Any]], seed: int = SEED) -> list[dict[str, Any]]:
    """The same sections with their scores shuffled among them: the control, where any real
    link between findings and score is broken."""
    scores = [section["score"] for section in sections]
    random.Random(seed).shuffle(scores)
    return [{**section, "score": score} for section, score in zip(sections, scores, strict=True)]


def by_topic(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for statement in sorted({section["statement"] for section in sections}):
        own = [s for s in sections if s["statement"] == statement]
        shortfalls = [s for s in own if s["score"] in SHORTFALL]
        caught = [s for s in shortfalls if s["findings"]]
        agreeing = [s for s in caught if any(f["category"] == statement for f in s["findings"])]
        found[statement] = {
            "recall_score_2_or_below": flagged(shortfalls),
            "recall_score_1": flagged([s for s in own if s["score"] == 1]),
            "flag_rate_score_3": flagged([s for s in own if s["score"] == 3]),
            "category_agreement": proportion(len(agreeing), len(caught)),
        }
    return found


def flag_rate_3(table: Counts) -> float | None:
    flagged_3 = sum(c for (score, found), c in table.items() if score == 3 and found > 0)
    total_3 = sum(c for (score, _), c in table.items() if score == 3)
    return flagged_3 / total_3 if total_3 else None


def memory(
    sections: list[dict[str, Any]],
    published: dict[str, str],
    rounds: int = ROUNDS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Reports published on or before CUTOFF against later ones: AUROC and flag rate at score 3
    in each, and the before-minus-after differences with cluster-bootstrap intervals."""
    tables = {name: counts(group) for name, group in by_report(sections).items()}
    before = sorted(name for name in tables if published[name] <= CUTOFF)
    after = sorted(name for name in tables if published[name] > CUTOFF)
    measures = {"auroc_shortfall": lambda t: auroc(t, SHORTFALL, GOOD), "flag_rate_3": flag_rate_3}
    result: dict[str, Any] = {"reports_before": len(before), "reports_after": len(after)}
    rng = random.Random(seed)
    differences: dict[str, list[float]] = {key: [] for key in measures}
    for _ in range(rounds):
        table_before = merged([tables[name] for name in resample(before, rng)])
        table_after = merged([tables[name] for name in resample(after, rng)])
        for key, measure in measures.items():
            value_before = measure(table_before)
            value_after = measure(table_after)
            if value_before is not None and value_after is not None:
                differences[key].append(value_before - value_after)
    for key, measure in measures.items():
        result[key] = {
            "before": measure(merged([tables[name] for name in before])),
            "after": measure(merged([tables[name] for name in after])),
            "difference_interval": interval(differences[key]),
        }
    return result
