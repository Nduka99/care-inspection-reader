"""The results site, built from the public files in `site/` and from synthetic readings.

The attacks: markup in a model's reading must be shown as text and never become a tag, and every
page must carry its Content Security Policy before anything it loads. Each `test_sabotage_*`
switches the protection off and shows the attack then gets through, so the attack test is known
to be able to fail. The tags are counted by Python's own HTML parser, not by the site's code."""

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from inspection_reader import site

SITE = Path(__file__).resolve().parents[1] / "site"
ATTACK = '<script>alert(1)</script><img src="https://example.com/x.png">'


def public(name: str) -> Any:
    return json.loads((SITE / name).read_text(encoding="utf-8"))


class Tags(HTMLParser):
    """Every start tag in a page, in order, with its attributes."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {name: value or "" for name, value in attrs}))


def names(html: str) -> list[str]:
    return [tag for tag, _ in Tags(html).tags]


def policy_problems(html: str) -> list[str]:
    """What is wrong with a page's policy: it must come straight after the character set, before
    anything the page loads, and no script may be on the page at all."""
    tags = Tags(html).tags
    head = tags[tags.index(("head", {})) + 1 :]
    problems = []
    first = head[1] if len(head) > 1 else ("", {})
    if first != ("meta", {"http-equiv": "Content-Security-Policy", "content": site.POLICY}):
        problems.append("the policy is not the first thing after the character set")
    if any(tag == "script" for tag, _ in tags):
        problems.append("a script")
    for tag, attrs in tags:
        address = attrs.get("src", "") if tag != "link" else attrs.get("href", "")
        if address.startswith(("http:", "https:", "//")):
            problems.append(f"{tag} loads from another site")
    return problems


def attack_reading() -> dict[str, Any]:
    """A reading whose every text field carries markup."""
    finding = {"category": ATTACK, "quote": ATTACK, "reason": ATTACK, "section": 0}
    section = {"statement": ATTACK, "score": 1, "paragraphs": [ATTACK], "findings": [finding]}
    header = {"model": "qwen3.5-4b", "prompt": ATTACK, "sha256": ATTACK}
    return {"header": header, "sections": [section], "dropped": 0, "error": []}


def test_markup_in_a_reading_is_shown_as_text() -> None:
    page = site.example(attack_reading())
    assert "script" not in names(page)
    assert "img" not in names(page)
    assert "&lt;script&gt;" in page


def test_sabotage_without_escaping_markup_in_a_reading_becomes_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site, "escape", lambda text, quote=True: text)
    page = site.example(attack_reading())
    assert "script" in names(page)
    assert "img" in names(page)


def test_every_page_carries_its_policy_first_and_no_script() -> None:
    pages = site.build(public("results.json"), public("example-reading.json"))
    assert set(pages) == {"index.html", "example.html", "results.html", "method.html", "404.html"}
    for name, html in pages.items():
        assert policy_problems(html) == [], name
    assert "default-src 'none'" in site.POLICY


def test_sabotage_a_page_without_its_policy_or_with_a_script_is_caught() -> None:
    pages = site.build(public("results.json"), public("example-reading.json"))
    page = pages["index.html"]
    meta = f'<meta http-equiv="Content-Security-Policy" content="{site.POLICY}">\n'
    assert meta in page
    assert policy_problems(page.replace(meta, "")) != []
    with_script = page.replace("</main>", '<script src="https://example.com/x.js"></script></main>')
    assert len(policy_problems(with_script)) == 2


def test_every_link_between_pages_resolves() -> None:
    pages = site.build(public("results.json"), public("example-reading.json"))
    files = set(pages) | {"style.css", "icon.svg", ""}
    for name, html in pages.items():
        for tag, attrs in Tags(html).tags:
            address = attrs.get("href") or attrs.get("src") or ""
            if tag not in ("a", "link") or address.startswith(("http:", "https:", "#")):
                continue
            assert address.lstrip("/") in files, (name, address)


def test_quotes_are_highlighted_where_they_stand() -> None:
    text = "Calls were late. Two carers had no checks; records were kept."
    html = site.highlighted(text, [(1, "Two carers had no checks"), (2, "not in this text")])
    assert html.count("<mark>") == 1
    assert "<mark>Two carers had no checks</mark>" in html
    assert html.startswith("Calls were late. <mark>")


def test_overlapping_quotes_share_one_highlight() -> None:
    text = "Calls were late and short, every day."
    html = site.highlighted(text, [(1, "Calls were late"), (2, "late and short")])
    assert html.count("<mark>") == 1
    assert "<mark>Calls were late and short</mark>" in html
    assert "</span>1,2</sup>" in html


def test_score_two_alone_is_the_difference_of_the_two_shares() -> None:
    results = public("results.json")
    chosen = results["test"]["chosen"]
    found = chosen["recall_score_2_or_below"]["found"] - chosen["recall_score_1"]["found"]
    assert results["sets"]["test"]["by_score"]["2"] == 449
    assert f"{found} of 449" in site.flagged_by_score(results)


def test_numbers_are_written_one_way() -> None:
    assert site.percent(1.0) == "100%"
    assert site.percent(0.0857) == "8.6%"
    assert site.interval({"low": 0.9862, "high": 1.0}) == "98.6–100%"
    assert site.decimal(-0.0014) == "−0.001"
    assert site.count(3610) == "3,610"
