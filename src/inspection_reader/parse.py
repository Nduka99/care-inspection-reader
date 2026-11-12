"""The Safe page of a CQC report as plain data: one section per quality statement.

On the page, each statement is a `<div class="report-keyquestion-title">` holding an `<h3>` name
and a `quality-score` div, followed by the inspectors' paragraphs. The key question itself has
the same kind of block, holding the rating banner, followed by an overview that states the rating
and any breaches of regulation. The name, score, banner and overview are labels or give them
away, so they are kept apart from the text the model reads (`model_text`). This leak guard
works on the page's structure, never on words.
"""

import re
from html.parser import HTMLParser
from typing import Any

TITLE_CLASS = "report-keyquestion-title"
SCORE_CLASS = "quality-score"
BANNER_CLASS = "rating__value"
# The report body ends where the "Page top" link starts; the page footer follows it.
END_CLASS = "back-to-top"
# Shorter sections are headings or placeholders with no assessment text of their own (first
# scores were set from old ratings, with no new text).
MIN_WORDS = 20


class SafePage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[dict[str, Any]] = []
        self.rating = ""
        self.ended = False
        self.title_depth = 0  # depth inside the open title block; 0 when outside
        self.capture = ""  # "name", "score" or "banner" while inside that element
        self.capture_depth = 0
        self.paragraph_depth = 0
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.ended:
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and END_CLASS in classes:
            self.ended = True
            return
        if tag == "div" and TITLE_CLASS in classes and not self.title_depth:
            self.blocks.append({"name": "", "score": None, "paragraphs": []})
            self.title_depth = 1
            return
        if self.title_depth:
            if tag == "div":
                self.title_depth += 1
            if self.capture:
                self.capture_depth += 1
            elif tag == "h3":
                self.start_capture("name")
            elif SCORE_CLASS in classes:
                self.start_capture("score")
            elif BANNER_CLASS in classes:
                self.start_capture("banner")
            return
        if tag == "p" and self.blocks:
            self.paragraph_depth += 1

    def start_capture(self, what: str) -> None:
        self.capture = what
        self.capture_depth = 1
        self.buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self.ended:
            return
        if self.title_depth:
            if self.capture:
                self.capture_depth -= 1
                if self.capture_depth == 0:
                    self.end_capture()
            if tag == "div":
                self.title_depth -= 1
            return
        if tag == "p" and self.paragraph_depth:
            self.paragraph_depth -= 1
            text = clean("".join(self.buffer))
            if text:
                self.blocks[-1]["paragraphs"].append(text)
            self.buffer = []

    def end_capture(self) -> None:
        text = clean("".join(self.buffer))
        block = self.blocks[-1]
        if self.capture == "name":
            block["name"] = text
        elif self.capture == "score":
            digits = re.findall(r"\d", text)
            block["score"] = int(digits[-1]) if digits else None
        else:
            self.rating = text
        self.capture = ""
        self.buffer = []

    def handle_data(self, data: str) -> None:
        if not self.ended and (self.capture or self.paragraph_depth):
            self.buffer.append(data)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse(html: str) -> dict[str, Any]:
    """The key question's rating and overview, and its scored sections with their text."""
    page = SafePage()
    page.feed(html)
    page.close()
    overview: list[str] = []
    sections = []
    for block in page.blocks:
        if block["score"] is None:
            overview += block["paragraphs"]
            continue
        words = sum(len(paragraph.split()) for paragraph in block["paragraphs"])
        if words >= MIN_WORDS:
            sections.append(
                {
                    "statement": block["name"],
                    "score": block["score"],
                    "paragraphs": block["paragraphs"],
                }
            )
    return {"rating": page.rating, "overview": overview, "sections": sections}


def model_text(section: dict[str, Any]) -> str:
    """The text the model reads for one section: its paragraphs only."""
    return "\n".join(section["paragraphs"])
