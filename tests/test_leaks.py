"""The publish scan (threat model T7), on planted synthetic data. Each test passes only when the
planted leak is found; each `test_sabotage_*` switches one part of the scan off and shows the
leak then goes through."""

import json
import re
from pathlib import Path

import pytest

from inspection_reader import leaks

REPORT = (
    "Staff at the Larkfield branch did not always arrive within the agreed window for "
    "time-critical medicines, and two people missed their evening doses last spring."
)
STOCK = "Every carer checked the kettle flex and the hallway rug at each and every visit."
OTHER = "The manager had started weekly audits of the electronic records after our visit."
# Built at run time, so this file never holds an ID in CQC's form and passes the scan itself.
PLANTED_ID = "1-" + "9" * 9


def reports(stock_providers: int) -> list[tuple[str, str]]:
    found = [("provider-a", REPORT), ("provider-b", OTHER)]
    found += [(f"stock-{n}", STOCK) for n in range(stock_providers)]
    return found


NAMES = ["Larkfield Care Services", "QUILLON"]
SECRET = leaks.private_runs(reports(stock_providers=5))


def test_a_planted_id_name_and_report_sentence_are_each_found() -> None:
    planted = {
        "README.md": f"See location {PLANTED_ID} for the source.",
        "site/index.html": "<p>Larkfield Care Services was read.</p>",
        "site/results.json": json.dumps({"note": REPORT[:120]}),
    }
    found = leaks.findings(planted, NAMES, SECRET)
    assert [line.split(":")[0] for line in found] == [
        "README.md",
        "site/index.html",
        "site/results.json",
    ]
    assert PLANTED_ID in found[0] and "name" in found[1] and "words from a report" in found[2]


def test_clean_text_and_stock_wording_have_no_findings() -> None:
    texts = {"README.md": "It reads home care reports. " + STOCK, "code.py": "x = 'quillon'"}
    assert leaks.findings(texts, NAMES, SECRET) == []


def test_wording_shared_by_fewer_than_five_providers_is_still_private() -> None:
    four = leaks.private_runs(reports(stock_providers=4))
    assert leaks.findings({"a.md": STOCK}, [], four) != []


def test_punctuation_and_case_do_not_hide_a_sentence() -> None:
    disguised = REPORT.upper().replace(",", " ;").replace("-", " ")
    assert leaks.findings({"a.md": disguised}, [], SECRET) != []


def test_sabotage_without_report_runs_a_planted_sentence_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leaks, "runs", lambda text: set())
    assert leaks.findings({"a.md": REPORT}, NAMES, SECRET) == []


def test_sabotage_without_the_id_pattern_a_planted_id_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leaks, "CQC_ID", re.compile(r"(?!)"))
    assert leaks.findings({"a.md": f"location {PLANTED_ID}"}, NAMES, SECRET) == []


def test_the_oracle_is_read_from_the_directory_and_the_cached_reports(tmp_path: Path) -> None:
    (tmp_path / "raw" / "directory").mkdir(parents=True)
    title = "CQC Locations data\n\n\n\n"
    header = '"Name","Also known as","Provider name","CQC Location ID (for office use only)"\n'
    rows = '"Larkfield Care Services","","Larkfield Ltd","loc-9"\n"Other","","","loc-5"\n'
    (tmp_path / "raw" / "directory" / "d.csv").write_text(title + header + rows, encoding="utf-8")
    (tmp_path / "sample.json").write_text('[{"location": "loc-9"}]', encoding="utf-8")
    (tmp_path / "reports" / "test").mkdir(parents=True)
    report = {"provider": "provider-a", "overview": [OTHER], "sections": [{"paragraphs": [REPORT]}]}
    (tmp_path / "reports" / "test" / "r.json").write_text(json.dumps(report), encoding="utf-8")
    names, secret = leaks.load_oracle(tmp_path)
    assert names == ["Larkfield Care Services", "Larkfield Ltd"]
    # A report's overview and paragraphs are read as one text, so runs also cross paragraphs.
    assert leaks.runs(OTHER + "\n" + REPORT) == secret
