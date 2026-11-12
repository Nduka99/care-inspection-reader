"""`inspection-reader read` on the synthetic page, with a stand-in for the model."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from inspection_reader import cli, llm, models

PAGE = Path(__file__).parent / "fixtures" / "safe_page.html"


@contextmanager
def stand_in(name: str, port: int, log: Path) -> Iterator[str]:
    yield "http://model"


def test_each_finding_sits_with_its_own_section_and_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def chat(url: str, system: str, user: str, schema: object, max_tokens: int) -> object:
        quote = "Records of creams were not always completed"
        found = [{"category": "Medicines optimisation", "quote": quote, "reason": "r"}]
        return {"findings": found if quote in user else []}

    monkeypatch.setattr(models, "served", stand_in)
    monkeypatch.setattr(models, "entry", lambda name: {"sha256": "abc"})
    monkeypatch.setattr(llm, "chat", chat)
    out = tmp_path / "reading.json"
    cli.main(["read", "--model", "m", "--out", str(out), str(PAGE)])
    reading = json.loads(out.read_text(encoding="utf-8"))
    by_section = [(s["statement"], s["score"], len(s["findings"])) for s in reading["sections"]]
    assert by_section == [
        ("Learning culture", 3, 0),
        ("Safe and effective staffing", 1, 0),
        ("Medicines optimisation", 2, 1),
    ]
    assert reading["header"]["sha256"] == "abc"
    assert reading["dropped"] == 0 and reading["error"] == []
