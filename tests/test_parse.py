"""The parser and its leak guard (threat model T2), on a synthetic page."""

from pathlib import Path

from inspection_reader.parse import model_text, parse

PAGE = parse((Path(__file__).parent / "fixtures" / "safe_page.html").read_text(encoding="utf-8"))


def test_sections_scores_rating_and_overview_are_read() -> None:
    assert PAGE["rating"] == "Requires improvement"
    assert [(s["statement"], s["score"]) for s in PAGE["sections"]] == [
        ("Learning culture", 3),
        ("Safe and effective staffing", 1),
        ("Medicines optimisation", 2),
    ]
    assert (
        PAGE["sections"][0]["paragraphs"][1]
        == "People said the office listened when they raised a worry."
    )
    assert any("OVERVIEW-SENTENCE" in line for line in PAGE["overview"])


def test_a_section_without_enough_text_is_left_out() -> None:
    assert "Safe environments" not in [s["statement"] for s in PAGE["sections"]]


def test_the_footer_after_the_report_body_is_not_read() -> None:
    every_line = PAGE["overview"] + [p for s in PAGE["sections"] for p in s["paragraphs"]]
    assert not any("FOOTER-SENTENCE" in line for line in every_line)


def label_strings() -> list[str]:
    """The labels, as the parser read them apart from the text: the oracle for the leak test."""
    found = [PAGE["rating"], *PAGE["overview"]]
    for section in PAGE["sections"]:
        found += [section["statement"], f"Score: {section['score']}"]
    return found


def leaks(text: str) -> list[str]:
    return [label for label in label_strings() if label.lower() in text.lower()]


def test_the_model_never_sees_headings_scores_rating_or_overview() -> None:
    for section in PAGE["sections"]:
        assert leaks(model_text(section)) == []


def test_sabotage_letting_headings_through_is_caught() -> None:
    with_headings = "\n\n".join(
        section["statement"] + "\n" + "\n".join(section["paragraphs"])
        for section in PAGE["sections"]
    )
    assert leaks(with_headings) == [
        "Learning culture",
        "Safe and effective staffing",
        "Medicines optimisation",
    ]
