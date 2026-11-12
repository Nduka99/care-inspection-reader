"""The analyses in `analysis.py`: each measure on hand-made sections with a known
answer. No real report text is used."""

import random
from typing import Any

from inspection_reader import analysis


def section(location: str, score: int, findings: int) -> dict[str, Any]:
    return {
        "location": location,
        "statement": "Safeguarding",
        "score": score,
        "findings": [{"category": "Safeguarding"}] * findings,
    }


def test_auroc_is_one_when_every_shortfall_has_more_findings() -> None:
    table = analysis.counts([section("a", 1, 3), section("a", 2, 2), section("b", 3, 0)])
    assert analysis.auroc(table, analysis.SHORTFALL, analysis.GOOD) == 1.0


def test_auroc_is_zero_when_reversed_and_a_half_when_all_tie() -> None:
    reversed_table = analysis.counts([section("a", 1, 0), section("b", 4, 2)])
    tied = analysis.counts([section("a", 1, 1), section("b", 3, 1)])
    assert analysis.auroc(reversed_table, analysis.SHORTFALL, analysis.GOOD) == 0.0
    assert analysis.auroc(tied, analysis.SHORTFALL, analysis.GOOD) == 0.5


def test_auroc_is_none_without_both_groups() -> None:
    table = analysis.counts([section("a", 1, 3)])
    assert analysis.auroc(table, analysis.SHORTFALL, analysis.GOOD) is None


def test_tau_b_is_one_for_a_perfect_order_and_minus_one_reversed() -> None:
    ordered = [section("a", 4, 0), section("a", 3, 1), section("a", 2, 2), section("a", 1, 3)]
    backwards = [section("a", 1, 0), section("a", 2, 1), section("a", 3, 2), section("a", 4, 3)]
    assert analysis.tau_b(analysis.counts(ordered)) == 1.0
    assert analysis.tau_b(analysis.counts(backwards)) == -1.0


def test_tau_b_matches_a_pair_by_pair_count_with_ties() -> None:
    """An independent count: every pair is counted directly, then tau-b's tie correction applied."""
    rng = random.Random(1)
    sections = [section("a", rng.randint(1, 4), rng.randint(0, 3)) for _ in range(60)]
    xs = [len(s["findings"]) for s in sections]
    ys = [5 - s["score"] for s in sections]
    concordant = discordant = tied_x = tied_y = 0
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            sign = (xs[i] - xs[j]) * (ys[i] - ys[j])
            concordant += sign > 0
            discordant += sign < 0
            tied_x += xs[i] == xs[j]
            tied_y += ys[i] == ys[j]
    pairs = len(xs) * (len(xs) - 1) / 2
    expected = (concordant - discordant) / ((pairs - tied_x) * (pairs - tied_y)) ** 0.5
    assert abs(analysis.tau_b(analysis.counts(sections)) - expected) < 1e-12


def test_a_resample_draws_whole_reports() -> None:
    sizes = {"small": 1, "large": 100}
    rng = random.Random(3)
    for _ in range(50):
        drawn = analysis.resample(sorted(sizes), rng)
        assert sum(sizes[name] for name in drawn) in {2, 101, 200}


def test_shuffling_keeps_the_scores_but_breaks_the_link() -> None:
    sections = [section(str(i), 1 + i % 4, 3 - i % 4) for i in range(400)]
    mixed = analysis.shuffled(sections)
    assert sorted(s["score"] for s in mixed) == sorted(s["score"] for s in sections)
    value = analysis.auroc(analysis.counts(mixed), analysis.SHORTFALL, analysis.GOOD)
    assert value is not None and abs(value - 0.5) < 0.1


def test_the_memory_split_is_inclusive_of_the_cutoff_day() -> None:
    sections = [
        section("old", 1, 2),
        section("old", 3, 0),
        section("new", 1, 2),
        section("new", 3, 1),
    ]
    published = {"old": analysis.CUTOFF, "new": "2025-02-01"}
    result = analysis.memory(sections, published, rounds=20)
    assert (result["reports_before"], result["reports_after"]) == (1, 1)
    assert result["flag_rate_3"]["before"] == 0.0
    assert result["flag_rate_3"]["after"] == 1.0
