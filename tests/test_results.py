"""The public results file on synthetic reports and runs: hand-worked numbers, and the attacks on
it. The allow-list must refuse a per-report field, and the check must catch a number that differs
from the runs. Each `test_sabotage_*` switches the protection off and shows the attack then goes
through, so the attack test is known to be able to fail."""

import json
from pathlib import Path
from typing import Any

import pytest

from inspection_reader import cli, results
from inspection_reader.extract import STATEMENTS

CARRIED = (
    "We did not look at Safeguarding during this assessment. The score for this quality "
    "statement is based on the previous rating for Safe."
)


def report(location: str, scores: list[int], carried: int | None = None) -> dict[str, Any]:
    """One synthetic report with a section for each of the eight statements, in order."""
    sections = []
    for index, (statement, score) in enumerate(zip(STATEMENTS, scores, strict=True)):
        text = CARRIED if index == carried else "Invented text about this part of the service."
        sections.append({"statement": statement, "score": score, "paragraphs": [text]})
    return {"location": location, "sections": sections}


def run(flagged: list[int], dropped: int = 0) -> dict[str, Any]:
    statements = list(STATEMENTS)
    findings = [{"category": statements[i], "section": i} for i in flagged]
    return {"findings": findings, "dropped": dropped}


SAMPLED = [
    {"location": "t1", "rating": "Inadequate"},
    {"location": "d1", "rating": "Good"},
    {"location": "no-text", "rating": "Good"},
]
# Scores by statement, in the order of STATEMENTS.
REPORTS = {
    "dev": [report("d1", [3, 3, 3, 3, 3, 3, 3, 3], carried=0)],
    "test": [report("t1", [1, 1, 2, 2, 3, 3, 4, 2])],
}
RUNS = {
    "dev": {results.CHOSEN: {"d1": run([])}, results.COMPARED: {"d1": run([1])}},
    "test": {
        # Shortfalls are sections 0, 1, 2, 3 and 7. Both catch 0 and 1; neither catches 2;
        # only the compared model catches 3 and 7. The chosen model also flags section 4.
        results.CHOSEN: {"t1": run([0, 1, 4], dropped=1)},
        results.COMPARED: {"t1": run([0, 1, 3, 7])},
    },
}


REAL_BUILD = results.build


def built() -> dict[str, Any]:
    """A fresh build, by the real function even while a test replaces `results.build`."""
    return REAL_BUILD(SAMPLED, REPORTS, RUNS)


def test_numbers_match_hand_worked_answers() -> None:
    data = built()
    assert data["sample"]["agencies"] == {
        "Inadequate": 1,
        "Requires improvement": 0,
        "Good": 2,
        "Outstanding": 0,
    }
    assert data["sample"]["with_scored_text"]["Good"] == 1
    assert data["sets"]["dev"] == {
        "reports": 1,
        "sections": 7,
        "carried_over_left_out": 1,
        "by_score": {"1": 0, "2": 0, "3": 7, "4": 0},
    }
    assert data["sets"]["test"]["by_score"] == {"1": 2, "2": 3, "3": 2, "4": 1}
    chosen = data["test"]["chosen"]
    assert (chosen["recall_score_2_or_below"]["found"], chosen["flag_rate_score_3"]["found"]) == (
        2,
        1,
    )
    assert (chosen["quote_drops"]["found"], chosen["quote_drops"]["total"]) == (1, 4)
    assert data["dev"]["compared"]["flag_rate_score_3"]["found"] == 1
    assert data["paired_test"] == {
        "shortfalls_caught_by_chosen_only": 0,
        "shortfalls_caught_by_compared_only": 2,
        "shortfalls_missed_by_both": 1,
        "p_exact": 0.5,
    }
    assert data["by_statement_test"]["Safeguarding"]["recall_score_2_or_below"]["found"] == 0
    assert results.problems(data) == []


def test_sign_test_matches_hand_worked_values() -> None:
    assert results.sign_test(0, 7) == 2 / 2**7
    assert results.sign_test(3, 3) == 1.0
    assert results.sign_test(0, 0) == 1.0


def test_hand_read_counts_add_up() -> None:
    kinds = [v for k, v in results.READ_BY_HAND.items() if k != "good_flags_sampled"]
    assert sum(kinds) == results.READ_BY_HAND["good_flags_sampled"]


PER_REPORT = {"location": "t1", "statement": "Safeguarding"}


@pytest.mark.parametrize(
    "plant",
    [
        lambda d: d["test"]["chosen"].update({"missed_score_1": [PER_REPORT]}),
        lambda d: d["by_statement_test"]["Safeguarding"].update({"t1": 1}),
        lambda d: d["sets"]["test"].update({"reports": ["t1"]}),
    ],
)
def test_a_per_report_field_is_refused(plant: Any) -> None:
    data = built()
    plant(data)
    assert results.problems(data) != []


@pytest.fixture
def private_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The CLI's private inputs, replaced by the synthetic ones; returns the results path."""
    (tmp_path / "sample.json").write_text(json.dumps(SAMPLED), encoding="utf-8")
    monkeypatch.setattr(cli, "DATA", tmp_path)
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "site" / "results.json")
    monkeypatch.setattr(cli, "reports_of", lambda split: REPORTS[split])
    monkeypatch.setattr(cli, "runs_of", lambda split, model: RUNS[split][model])
    return tmp_path / "site" / "results.json"


def leaky_build(*args: Any) -> dict[str, Any]:
    data = built()
    data["test"]["chosen"]["missed_score_1"] = [PER_REPORT]
    return data


def test_a_per_report_field_is_never_written(
    private_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(results, "build", leaky_build)
    with pytest.raises(SystemExit):
        cli.main(["results"])
    assert not private_data.exists()


def test_sabotage_without_the_allow_list_a_per_report_field_is_written(
    private_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(results, "build", leaky_build)
    monkeypatch.setattr(results, "problems", lambda data: [])
    cli.main(["results"])
    assert "missed_score_1" in private_data.read_text(encoding="utf-8")


def changed_count(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["test"]["chosen"]["recall_score_1"]["found"] -= 1
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_changed_number_is_caught(private_data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["results"])
    cli.main(["results", "--check"])
    changed_count(private_data)
    with pytest.raises(SystemExit):
        cli.main(["results", "--check"])
    assert (
        "test/chosen/recall_score_1/found: 1 in the file, 2 from the runs"
        in capsys.readouterr().out
    )


def test_sabotage_without_the_comparison_a_changed_number_passes(
    private_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.main(["results"])
    changed_count(private_data)
    monkeypatch.setattr(results, "differences", lambda committed, fresh: [])
    cli.main(["results", "--check"])
