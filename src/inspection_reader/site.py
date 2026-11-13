"""The results site: static pages built from the public files in `site/`.

- `build(results, reading)` returns each page's file name and HTML. It reads and writes no
  files; the `site` command does that.
- Every value taken from a data file passes through `escape` before it enters a page. The
  example reading is a model's output, so it is untrusted: markup in it is shown as text and
  never runs.
- Every page carries a Content Security Policy that lets it load only this site's stylesheet and
  icon, so no script runs and nothing loads from another site. GitHub Pages cannot send response
  headers, so the policy is a meta tag, the first thing in the head.
- Every number comes from the results file; none is typed in here.
"""

from html import escape
from typing import Any

from inspection_reader.extract import MAX_FINDINGS, STATEMENTS
from inspection_reader.quotes import locate
from inspection_reader.sample import DEV_SHARE

POLICY = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"
NAME = "Care inspection reader"
# Short names, so the four fit one row on a phone; each page's own heading gives its full name.
PAGES = (
    ("index.html", "Overview"),
    ("example.html", "Example"),
    ("results.html", "Results"),
    ("method.html", "Method"),
)
# CQC's wording for each score of a quality statement.
SCORES = {
    1: "significant shortfalls",
    2: "some shortfalls",
    3: "a good standard",
    4: "an exceptional standard",
}
SCORE_TONES = {1: "today", 2: "visit", 3: "", 4: "done"}
MODEL_NAMES = {"qwen3.5-4b": "Qwen3.5-4B", "gemma-4-e4b": "Gemma 4 E4B"}
RATINGS = ("Inadequate", "Requires improvement", "Good", "Outstanding")
REPOSITORY = "https://github.com/Nduka99/care-inspection-reader"
RESULTS_FILE = f"{REPOSITORY}/blob/main/site/results.json"
# The companion project: the same extraction method on synthetic care notes, with a live demo.
COMPANION = "https://care.ndukanwagbo.com"
COMPANION_REPOSITORY = "https://github.com/Nduka99/homecare_intelligence"
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
MARK = (
    '<svg class="mark" viewBox="0 0 512 512" aria-hidden="true" focusable="false">'
    '<rect width="512" height="512" rx="112" fill="#1d7a48"/>'
    '<rect x="136" y="112" width="240" height="288" rx="28" fill="#ffffff"/>'
    '<path d="M184 168H328M184 212H328" stroke="#c3cbd2" stroke-width="16" '
    'stroke-linecap="round"/>'
    '<circle cx="250" cy="292" r="50" fill="none" stroke="#1d7a48" stroke-width="26"/>'
    '<path d="M286 328l44 44" stroke="#1d7a48" stroke-width="26" stroke-linecap="round"/>'
    "</svg>"
)

Results = dict[str, Any]
Proportion = dict[str, Any]


# Numbers, written the same way on every page.


def count(number: int) -> str:
    return f"{number:,}"


def percent(rate: float) -> str:
    return f"{rate * 100:.1f}".removesuffix(".0") + "%"


def fraction(p: Proportion) -> str:
    return f"{count(p['found'])}/{count(p['total'])}"


def interval(p: Proportion) -> str:
    return f"{percent(p['low']).removesuffix('%')}–{percent(p['high'])}"


def decimal(value: float) -> str:
    """Three places, with a true minus sign."""
    return f"{value:.3f}".replace("-", "−")


def stacked(figure: str, below: str) -> str:
    """A table cell's figure with a second, quieter figure on the line below it."""
    return f'{figure}<span class="below">{below}</span>'


def estimate(measure: dict[str, float]) -> str:
    low, high = decimal(measure["low"]), decimal(measure["high"])
    return f"{decimal(measure['value'])} ({low} to {high})"


# The parts every page shares.


def shell(name: str, title: str, main: str, root: str = "", tag: str = "") -> str:
    """One page: the app bar with the page switch, the main content and the footer. Links are
    relative, so the site works at any address; `root` is "/" for the not-found page, which
    the host serves at whatever address was asked for. A `tag` sits in the app bar after the
    name, as the home-care app shows its SYNTHETIC tag."""
    links = []
    for file, label in PAGES:
        current = ' aria-current="page"' if file == name else ""
        links.append(f'<a href="{root}{file}"{current}>{label}</a>')
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{POLICY}">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a2025" media="(prefers-color-scheme: dark)">
<title>{title} · {NAME}</title>
<link rel="stylesheet" href="{root}style.css">
<link rel="icon" href="{root}icon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">Skip to the main content</a>
<header class="appbar">
<div class="appbar-inner">
<a class="brand" href="{root}index.html">{MARK}<span class="brand-name">{NAME}</span></a>{tag}
<nav class="pages" aria-label="Pages">{"".join(links)}</nav>
</div>
</header>
<main id="main" class="page">
{main}
</main>
<footer class="footer">
<p>Contains CQC information licensed under the <a href="{OGL}">Open Government Licence v3.0</a>.
Not connected with or endorsed by the Care Quality Commission (CQC).</p>
<p>No report text, provider name or location name appears on this site. Code and method:
<a href="{REPOSITORY}">the project on GitHub</a> (MIT licence).</p>
<p>Companion project: <a href="{COMPANION}">Home-care intelligence</a>, the same method on
synthetic care notes.</p>
</footer>
</body>
</html>
"""


def head(title: str, sub: str) -> str:
    return f'<div class="page-head"><h1>{title}</h1><p class="sub">{sub}</p></div>'


def card(heading_id: str, heading: str, body: str) -> str:
    return (
        f'<section class="card" aria-labelledby="{heading_id}">'
        f'<h2 id="{heading_id}">{heading}</h2>{body}</section>'
    )


def table(caption: str, columns: list[str], rows: list[list[str]]) -> str:
    """A table whose first column names each row and whose other columns are figures. Cells
    are HTML, already escaped by the caller."""
    head_cells = f'<th scope="col">{columns[0]}</th>'
    head_cells += "".join(f'<th scope="col" class="number">{c}</th>' for c in columns[1:])
    body = []
    for row in rows:
        cells = f'<th scope="row">{row[0]}</th>'
        cells += "".join(f'<td class="number">{cell}</td>' for cell in row[1:])
        body.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="table-frame"><table><caption>{caption}</caption>'
        f"<thead><tr>{head_cells}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def meter(name: str, detail: str, found: int, total: int) -> str:
    """One row of the meter list: the share as a bar on a track, with its figures beside it.
    The bar is drawn only; the figures say the same in words."""
    rate = found / total
    fill = ""
    if found:
        fill = f'<rect class="fill" width="{rate * 100:.2f}%" height="100%" rx="6"/>'
    return (
        f'<li><span class="name">{name} <span>· {detail}</span></span>'
        f'<span class="share">{count(found)} of {count(total)} · {percent(rate)}</span>'
        f'<svg aria-hidden="true" focusable="false">'
        f'<rect class="track" width="100%" height="100%" rx="6"/>{fill}</svg></li>'
    )


def score_tag(score: int) -> str:
    tone = SCORE_TONES[score]
    classes = f"tag {tone}" if tone else "tag"
    return f'<span class="{classes}">Score {score} · {SCORES[score]}</span>'


# The overview.


def flagged_by_score(results: Results) -> str:
    """The headline: the share of test sections flagged at each score, in two groups with
    opposite goals, so a short bar is read as good where it is good. The file holds scores 1
    and 1 or 2 together, so score 2 alone is their difference."""
    chosen = results["test"]["chosen"]
    one = chosen["recall_score_1"]
    one_or_two = chosen["recall_score_2_or_below"]
    shortfalls = [
        meter("Score 1", SCORES[1], one["found"], one["total"]),
        meter(
            "Score 2",
            SCORES[2],
            one_or_two["found"] - one["found"],
            one_or_two["total"] - one["total"],
        ),
    ]
    good = []
    for score in (3, 4):
        p = chosen[f"flag_rate_score_{score}"]
        good.append(meter(f"Score {score}", SCORES[score], p["found"], p["total"]))
    return (
        '<h3 class="group">Sections with shortfalls: should be flagged</h3>'
        f'<ul class="meters">{"".join(shortfalls)}</ul>'
        '<h3 class="group">Sections at a good standard or better: should not be flagged</h3>'
        f'<ul class="meters">{"".join(good)}</ul>'
    )


def overview(results: Results) -> str:
    test = results["sets"]["test"]
    chosen = results["test"]["chosen"]
    shortfalls = percent(chosen["recall_score_2_or_below"]["rate"])
    good = percent(chosen["flag_rate_score_3"]["rate"])
    exceptional = percent(chosen["flag_rate_score_4"]["rate"])
    headline = (
        f"<p>The test set: {count(test['reports'])} reports and {count(test['sections'])} "
        "scored sections, read once, with nothing tuned on them. A section is flagged when "
        "the model gives at least one finding whose quote is really in that section. "
        "Flagging every section would also catch every shortfall, so the gap between the two "
        "groups is what counts.</p>"
        f"{flagged_by_score(results)}"
        '<p>Intervals and every other measure are on the <a href="results.html">results '
        "page</a>.</p>"
    )
    terms = (
        '<dl class="details">'
        "<dt>Section</dt><dd>One of the eight Safe quality statements in one report, such as "
        "Safeguarding or Medicines optimisation.</dd>"
        "<dt>Score</dt><dd>The inspectors' score for that statement: 1 significant shortfalls, "
        "2 some shortfalls, 3 a good standard, 4 an exceptional standard.</dd>"
        "<dt>Finding</dt><dd>A concern the model names: its category, the exact words it rests "
        "on and a one-sentence reason. Code checks that the words are in the section.</dd>"
        "<dt>Flagged</dt><dd>A section with at least one finding, whatever statement the "
        "finding is filed under.</dd>"
        "<dt>Test set</dt><dd>Reports kept aside and read once, at the end, after every choice "
        "had been made on a separate development set.</dd>"
        "</dl>"
    )
    limits = (
        "<ul>"
        "<li>Inspectors' reports are not daily care notes: they are written for the public, by "
        "trained people.</li>"
        "<li>A score rests on more evidence than the page shows, so some shortfalls cannot be "
        "found from the text.</li>"
        "<li>A flag is a screen, not a grade: it says nothing about how serious a finding is."
        "</li>"
        "<li>The sample was drawn by rating, so its mix of scores is not England's. That is why "
        "results are given for each score.</li>"
        "<li>One prompt, and each model run once on the test set; run-to-run variation was not "
        "measured.</li>"
        "</ul>"
    )
    return (
        head(
            "Finding safety concerns in home care inspection reports",
            "A small language model, run on one laptop, reads the Safe part of the Care Quality "
            "Commission's inspection reports on home care agencies in England. It lists each "
            "safety concern it finds with the exact words it rests on, and code checks every "
            "quote. Its findings are then compared with the inspectors' own scores.",
        )
        + card(
            "headline",
            f"It flagged {shortfalls} of sections with shortfalls, {good} of good ones and "
            f"{exceptional} of exceptional ones",
            headline,
        )
        + card("terms", "What the words mean", terms)
        + card("limits", "What it does not show", limits)
        + '<p class="next"><a href="example.html">See the worked example</a>: the model reads '
        "an invented report, and every quote is shown in place.</p>"
    )


# The worked example.


def highlighted(text: str, quotes: list[tuple[int, str]]) -> str:
    """One paragraph as HTML, with each quote found in it highlighted and its finding's number
    after it. Overlapping quotes share one highlight."""
    spans = []
    for number, quote in quotes:
        found = locate(quote, text)
        if found is not None:
            spans.append((found[0], found[1], number))
    spans.sort()
    merged: list[tuple[int, int, list[int]]] = []
    for start, end, number in spans:
        if merged and start <= merged[-1][1]:
            last_start, last_end, numbers = merged[-1]
            merged[-1] = (last_start, max(last_end, end), [*numbers, number])
        else:
            merged.append((start, end, [number]))
    parts = []
    done = 0
    for start, end, numbers in merged:
        refs = ",".join(str(n) for n in numbers)
        parts.append(escape(text[done:start]))
        parts.append(
            f"<mark>{escape(text[start:end])}</mark>"
            f'<sup class="ref"><span class="visually-hidden">finding </span>{refs}</sup>'
        )
        done = end
    parts.append(escape(text[done:]))
    return "".join(parts)


def finding_item(number: int, finding: dict[str, Any], statement: str) -> str:
    elsewhere = ""
    if finding["category"] != statement:
        elsewhere = '<span class="tag visit">Another statement</span>'
    return (
        f'<li class="finding"><div class="finding-title"><h3 class="label">Finding {number}: '
        f"{escape(finding['category'])}</h3>{elsewhere}</div>"
        f'<p class="quote"><mark>“{escape(finding["quote"])}”</mark></p>'
        f'<p class="why">{escape(finding["reason"])}</p></li>'
    )


def outcome(score: int, flagged: bool) -> str:
    """The section's outcome as the results count it, and a line when it disagrees with the
    inspectors' score."""
    if flagged and score >= 3:
        return (
            '<p class="meta">Flagged, though the inspectors scored it '
            f'{score}: one of the <a href="results.html#good-flags">flags on good '
            "sections</a>.</p>"
        )
    if not flagged and score <= 2:
        return '<p class="meta">Not flagged, though the inspectors found shortfalls.</p>'
    return ""


def example_section(index: int, section: dict[str, Any]) -> str:
    findings = section["findings"]
    score = int(section["score"])
    quotes = [(n, f["quote"]) for n, f in enumerate(findings, start=1)]
    paragraphs = "".join(
        f'<p class="entry">{highlighted(text, quotes)}</p>' for text in section["paragraphs"]
    )
    if findings:
        items = "".join(
            finding_item(n, f, section["statement"]) for n, f in enumerate(findings, start=1)
        )
        listed = f'<ul class="findings" aria-label="Findings">{items}</ul>'
    else:
        listed = '<p class="empty">No findings.</p>'
    flagged = "Flagged" if findings else "Not flagged"
    heading_id = f"section-{index}"
    return (
        f'<section class="card" aria-labelledby="{heading_id}"><div class="card-head">'
        f'<h2 id="{heading_id}">{escape(section["statement"])}</h2>'
        f'{score_tag(score)}<span class="tag">{flagged}</span></div>'
        f"{outcome(score, bool(findings))}{paragraphs}{listed}</section>"
    )


def example(reading: dict[str, Any]) -> str:
    header = reading["header"]
    model = MODEL_NAMES[header["model"]]
    unanswered = len(reading["error"])
    answered = (
        "The model answered every section."
        if not unanswered
        else f"The model gave no usable answer for {unanswered} sections."
    )
    how = (
        "<p>Each card below is one section: the inspectors' score, and whether the model "
        "flagged it. The model saw only the section's paragraphs, never its name, its score or "
        "the rest of the report. Highlighted words are the quotes its findings rest on, each "
        "found in the text by code; the small number after a highlight is its finding. Under "
        "each quote is the model's own one-sentence reason. A finding the model filed under "
        "another statement than its section's is tagged Another statement; the section still "
        "counts as flagged.</p>"
        "<p>A finding whose quote is not in the text is dropped and counted, never repaired. "
        f"This reading dropped {count(reading['dropped'])}. {answered}</p>"
    )
    sections = "".join(example_section(i, s) for i, s in enumerate(reading["sections"]))
    provenance = (
        f"<p>Read once by {escape(model)} on one laptop GPU, at temperature 0. To read the same "
        "page yourself:</p>"
        "<pre><code>uv run inspection-reader read --model "
        f"{escape(header['model'])} site/example-page.html</code></pre>"
        '<details class="provenance"><summary>Run details</summary>'
        f"<p>Prompt SHA-256 <code>{escape(header['prompt'])}</code><br>"
        f"Model file SHA-256 <code>{escape(header['sha256'])}</code></p></details>"
    )
    return (
        head(
            "A worked example",
            "An invented Safe page in CQC's layout, and the chosen model's one reading of it, "
            "shown as it came, mistakes included.",
        )
        + '<p class="notice caution"><strong>Invented report.</strong> Every word of it is '
        "made up and describes no real service. No real report text appears anywhere on this "
        "site.</p>"
        + card("how", "How to read it", how)
        + sections
        + card("reading", "The reading", provenance)
        + '<p class="next"><a href="results.html">See the results</a>: how the model did on '
        "real reports, against the inspectors' scores.</p>"
    )


# The results.


def measure_rows(measures: dict[str, Any]) -> list[list[str]]:
    rows = []
    labels = (
        ("recall_score_1", "Sections scored 1 that were flagged"),
        ("recall_score_2_or_below", "Sections scored 1 or 2 that were flagged"),
        ("flag_rate_score_3", "Sections scored 3 (a good standard) that were flagged"),
        ("flag_rate_score_4", "Sections scored 4 (an exceptional standard) that were flagged"),
        ("category_agreement", "Flagged shortfalls with a finding under their own statement"),
        ("quote_drops", "Findings dropped because the quote was not in the text"),
    )
    for key, label in labels:
        p = measures[key]
        rows.append([label, fraction(p), stacked(percent(p["rate"]), interval(p))])
    rows.append(["Sections the model could not answer", count(measures["errors"]), ""])
    return rows


def by_statement(results: Results) -> str:
    """One row per statement, its three figures in a small grid: a list, not a table, so it
    fits a phone."""
    topics = results["by_statement_test"]
    rows = []
    misses = {}
    for statement in STATEMENTS:
        topic = topics[statement]
        agreement = topic["category_agreement"]
        misses[statement] = agreement["total"] - agreement["found"]
        cells = (
            f"<div><dt>Shortfalls flagged</dt>"
            f"<dd>{fraction(topic['recall_score_2_or_below'])}</dd></div>"
            f"<div><dt>Score 3 flagged</dt><dd>{fraction(topic['flag_rate_score_3'])}</dd></div>"
            f"<div><dt>Own statement</dt><dd>{fraction(agreement)}</dd></div>"
        )
        rows.append(
            f'<li><p class="name">{escape(statement)}</p><dl class="cells">{cells}</dl></li>'
        )
    worst = sorted(misses, key=lambda s: misses[s], reverse=True)[:2]
    total = sum(misses.values())
    return (
        "<p>Test set, chosen model. For each statement: the sections with shortfalls (scored "
        "1 or 2) that were flagged; the sections scored 3 that were flagged; and, of the "
        "flagged shortfalls, those with a finding filed under the section's own statement.</p>"
        f'<ul class="list statements">{"".join(rows)}</ul>'
        + f"<p>Of the {total} flagged shortfalls with no finding under their own statement, "
        f"{misses[worst[0]] + misses[worst[1]]} are in {escape(worst[0])} or "
        f"{escape(worst[1])}: the model filed the shortfall under a neighbouring statement, "
        "such as staffing. The section is still flagged.</p>"
    )


def model_choice(results: Results) -> str:
    chosen = MODEL_NAMES[results["models"]["chosen"]]
    compared = MODEL_NAMES[results["models"]["compared"]]
    dev = results["dev"]
    test = results["test"]
    paired = results["paired_test"]
    rule = (
        "<ol>"
        "<li>the higher share of sections scored 1 or 2 flagged;</li>"
        "<li>if the two are within two sections of each other, the lower share of sections "
        "scored 3 flagged;</li>"
        "<li>then the higher share of sections scored 1 flagged.</li>"
        "</ol>"
    )
    rows = []
    for key, label in (
        ("recall_score_1", "Sections scored 1 flagged"),
        ("recall_score_2_or_below", "Sections scored 1 or 2 flagged"),
        ("flag_rate_score_3", "Sections scored 3 flagged"),
        ("flag_rate_score_4", "Sections scored 4 flagged"),
    ):
        mine, theirs = test["chosen"][key], test["compared"][key]
        rows.append(
            [
                label,
                stacked(fraction(mine), percent(mine["rate"])),
                stacked(fraction(theirs), percent(theirs["rate"])),
            ]
        )
    dev_mine, dev_theirs = dev["chosen"], dev["compared"]
    return (
        f"<p>Two local models of about 4 billion parameters each were compared with the same "
        f"prompt: {chosen} and {compared}. The rule for choosing was written down before "
        "either ran, and used the development set only:</p>"
        + rule
        + f"<p>On the development set, {compared} flagged "
        f"{fraction(dev_theirs['recall_score_2_or_below'])} sections scored 1 or 2 and "
        f"{chosen} {fraction(dev_mine['recall_score_2_or_below'])}, within two. The second rule "
        f"decided: {chosen} flagged {fraction(dev_mine['flag_rate_score_3'])} sections scored 3 "
        f"({percent(dev_mine['flag_rate_score_3']['rate'])}) against {compared}'s "
        f"{fraction(dev_theirs['flag_rate_score_3'])} "
        f"({percent(dev_theirs['flag_rate_score_3']['rate'])}).</p>"
        f"<p>{compared} was also run once on the test set, so the cost of the choice is "
        "measured, not guessed.</p>"
        + table(
            "Test set, both models",
            ["Measure", f"{chosen} (chosen)", compared],
            rows,
        )
        + f"<p>Section by section, {compared} caught "
        f"{paired['shortfalls_caught_by_compared_only']} shortfall sections that {chosen} "
        f"missed, and {chosen} caught {paired['shortfalls_caught_by_chosen_only']} that "
        f"{compared} missed (exact two-sided sign test, p = {paired['p_exact']:.3f}). Read by "
        f"hand, each of the {paired['shortfalls_caught_by_compared_only']} states its shortfall "
        "in words, usually in one sentence inside a "
        f"mostly positive section. In return, {chosen} flagged "
        f"{test['chosen']['flag_rate_score_3']['found']} sections scored 3 against "
        f"{test['compared']['flag_rate_score_3']['found']}, and "
        f"{test['chosen']['flag_rate_score_4']['found']} scored 4 against "
        f"{test['compared']['flag_rate_score_4']['found']}. Both missed the same "
        f"{paired['shortfalls_missed_by_both']} shortfall "
        "sections; read by hand, their text describes no shortfall, so the score rests on "
        "evidence the page does not show.</p>"
    )


def good_flags(results: Results) -> str:
    read = results["read_by_hand"]
    flagged = results["test"]["chosen"]["flag_rate_score_3"]["found"]
    return (
        f"<p>A seeded random sample of {read['good_flags_sampled']} of the {flagged} was read "
        "by hand:</p><ul>"
        f"<li>{read['good_flags_real_minor']} are a real minor issue that the inspector noted "
        "and accepted;</li>"
        f"<li>{read['good_flags_misread']} are misreads, where a neutral or good statement was "
        "read as a shortfall, usually because of negative wording (a service that does not "
        "offer a task, or people who had no concerns to raise);</li>"
        f"<li>{read['good_flags_out_of_context']} is an old problem quoted as if it were "
        "current;</li>"
        f"<li>{read['good_flags_unclear']} is unclear.</li></ul>"
    )


def results_page(results: Results) -> str:
    test = results["sets"]["test"]
    grading = results["grading_test"]
    measures = (
        f"<p>{count(test['reports'])} reports and {count(test['sections'])} scored sections, "
        "read once with the chosen model. Each interval is a Wilson 95% interval: the range the "
        "true share is likely to lie in, given how many sections there were.</p>"
        + table(
            "Test set, chosen model; the share's 95% interval below it",
            ["Measure", "Count", "Share"],
            measure_rows(results["test"]["chosen"]),
        )
    )
    grades = (
        "<p>The model grades shortfalls without being asked to: the lower the score, the more "
        "findings. Each interval is a 95% interval from a bootstrap that resamples whole reports. "
        "Shuffling the scores among the sections is the control: with nothing to find, the "
        "measures should fall to chance, 0.5 and 0, and they do.</p>"
        f"<p>A section scored 1 or 2 has more findings than one scored 3 or 4 with a chance of "
        f"<strong>{estimate(grading['auroc_shortfall'])}</strong>, ties counted half (the area "
        f"under the ROC curve). With the scores shuffled: "
        f"{estimate(grading['shuffled_auroc_shortfall'])}.</p>"
        f"<p>Kendall's tau-b between the number of findings and severity (5 minus the score) is "
        f"<strong>{estimate(grading['tau_b'])}</strong>. With the scores shuffled: "
        f"{estimate(grading['shuffled_tau_b'])}.</p>"
    )
    return (
        head(
            "Results",
            f'Every number here is read from the project\'s <a href="{RESULTS_FILE}">public '
            "results file</a>, which its code builds from the saved model runs and checks "
            'against them. The words are defined on the <a href="index.html#terms">overview'
            "</a>.",
        )
        + card("measures", "The test set, read once", measures)
        + card("grading", "More findings go with worse scores", grades)
        + card("statements", "By statement", by_statement(results))
        + card("good-flags", "What a flag on a section scored 3 is", good_flags(results))
        + card("choice", "The model choice, and what it cost", model_choice(results))
        + '<p class="next"><a href="method.html">See the method</a>: how the reports were '
        "chosen and read, and how the work is checked.</p>"
    )


# Method and data.


def samples(results: Results) -> str:
    sample = results["sample"]
    sets = results["sets"]
    rating_rows = [
        [rating, count(sample["agencies"][rating]), count(sample["with_scored_text"][rating])]
        for rating in RATINGS
    ]
    rating_rows.append(
        [
            "All",
            count(sum(sample["agencies"].values())),
            count(sum(sample["with_scored_text"].values())),
        ]
    )
    set_rows = [
        ["Reports", count(sets["dev"]["reports"]), count(sets["test"]["reports"])],
        ["Scored sections", count(sets["dev"]["sections"]), count(sets["test"]["sections"])],
    ]
    for score in ("1", "2", "3", "4"):
        dev, test = sets["dev"]["by_score"][score], sets["test"]["by_score"][score]
        set_rows.append([f"Scored {score}", count(dev), count(test)])
    set_rows.append(
        [
            "Carried-over sections left out",
            count(sets["dev"]["carried_over_left_out"]),
            count(sets["test"]["carried_over_left_out"]),
        ]
    )
    return table(
        "Home care agencies by their Safe rating",
        ["Safe rating", "Sampled", "With a scored Safe page"],
        rating_rows,
    ) + table("The two sets", ["Count", "Development", "Test"], set_rows)


def method(results: Results) -> str:
    steps = (
        "<ol>"
        "<li><strong>Sample.</strong> From CQC's directory of rated care services: the home care "
        "agencies whose Safe rating was published from 1 January 2024, when CQC began scoring "
        "each quality statement. Score 1 is rare at random, so agencies were drawn by Safe "
        "rating: every Inadequate and Outstanding agency, and seeded random samples of the "
        "others.</li>"
        "<li><strong>Split by provider.</strong> One provider's agencies share policies and "
        "often wording, so each provider goes wholly to the development set (about "
        f"{DEV_SHARE}%) or the test set, by a hash of its ID. Every parsed report was frozen "
        "by its SHA-256 hash before any model ran.</li>"
        "<li><strong>Nothing gives the answer away.</strong> The model reads only a section's "
        "paragraphs: never the statement's name, its score, the rating banner or the overview. "
        "The guard works on the page's HTML structure, not on words.</li>"
        "<li><strong>Carried-over sections are left out.</strong> When CQC did not assess a "
        "statement again, its text says so and its score comes from an earlier rating, so the "
        "score says nothing about the text.</li>"
        "<li><strong>One call per section,</strong> with at most "
        f"{MAX_FINDINGS} findings each.</li>"
        "<li><strong>Findings.</strong> Each has a category (one of the eight statements), the "
        "exact words that state it and a one-sentence reason. The server holds the reply to a "
        "JSON schema and the code checks it again. Each quote is looked up in the section's "
        "text: a finding whose quote is not there is dropped and counted.</li>"
        "<li><strong>Untrusted text.</strong> Report text reaches the model as a JSON string, so "
        "nothing written in it can end the data field and pose as an instruction.</li>"
        "<li><strong>Models.</strong> Qwen3.5-4B and Gemma 4 E4B (Apache-2.0), as files pinned "
        "by SHA-256, served by llama.cpp on one laptop GPU with 8 GB, at temperature 0.</li>"
        "</ol>"
    )
    statements = "".join(
        f"<dt>{escape(name)}</dt><dd>{escape(meaning.capitalize())}.</dd>"
        for name, meaning in STATEMENTS.items()
    )
    checks = (
        "<p>Every protection has a test that carries out the attack and passes only when the "
        "attack fails, and a twin test that switches the protection off and shows the attack "
        "then succeeds, so the first test is known to be able to fail.</p>"
        "<ul>"
        "<li>A made-up quote is dropped.</li>"
        "<li>No statement name, score, banner or overview text reaches the model.</li>"
        "<li>Text that tries to close its data field stays inside it.</li>"
        "<li>No provider is in both sets.</li>"
        "<li>A path that robots.txt disallows is never fetched.</li>"
        "<li>The publishing scan finds a planted CQC ID, the name of a sampled service, or any "
        "run of 8 words from a fetched report.</li>"
        "<li>The results file refuses any field outside its list of allowed ones, and a number "
        "that differs from the runs is caught.</li>"
        "<li>Markup in a model's reading is shown on this site as text, never run.</li>"
        "</ul>"
    )
    run = (
        '<p>Needs <a href="https://docs.astral.sh/uv/">uv</a>. A read also needs llama.cpp\'s '
        "<code>llama-server</code>, on <code>PATH</code> or with its full path in "
        "<code>LLAMA_SERVER</code>, and the model file in <code>models/</code>, matching its "
        "size and SHA-256 in <code>models.json</code>. If either is missing, the command says "
        "what to do.</p>"
        "<pre><code>uv sync\n"
        "uv run python scripts/check.py\n"
        "uv run inspection-reader read --model qwen3.5-4b site/example-page.html</code></pre>"
        f'<p>The <a href="{REPOSITORY}">repository</a> explains how to rebuild the whole study '
        "from CQC's files.</p>"
    )
    data = (
        "<p>Contains CQC information licensed under the "
        f'<a href="{OGL}">Open Government Licence v3.0</a>. This project is not connected with '
        "or endorsed by CQC.</p>"
        "<ul>"
        "<li>Sources: CQC's care directory of 4 November 2026 and care directory with ratings "
        "of 2 November 2026, and the Safe page of each sampled agency's latest report with "
        "scored statements, fetched on 4 November 2026.</li>"
        "<li>No report text, provider name or location name is published, here or in the "
        "repository. The results are counts; the only report shown in full is invented.</li>"
        "</ul>"
    )
    why = (
        f'<p><a href="{COMPANION}">Home-care intelligence</a> reads carers\' notes with the same '
        "method: every finding quotes the words it rests on, and code checks the quote. Its "
        "notes are synthetic, written for the project, so they cannot show how the method does "
        "on writing by real people. Inspection reports can: real people wrote them, and the "
        "inspectors' scores, given independently before this project began, show where the "
        "shortfalls are.</p>"
        f"<p>Its live demo runs while the author's laptop is on; its code is <a href=\""
        f'{COMPANION_REPOSITORY}">on GitHub</a>.</p>'
    )
    return (
        head(
            "Method and data",
            "How the reports were chosen and read, how the work is checked, and where the data "
            "comes from.",
        )
        + card("why", "Why real reports", why)
        + card("how", "How it works", steps)
        + card("sets", "The sample and the two sets", samples(results))
        + card(
            "statements",
            "The eight Safe quality statements",
            "<p>As the model is told them, in this project's words.</p>"
            f'<dl class="details">{statements}</dl>',
        )
        + card("checks", "How it is checked", checks)
        + card("run", "Run it yourself", run)
        + card("data", "Data and credit", data)
        + f'<p class="next">The code and the whole study: <a href="{REPOSITORY}">the project '
        "on GitHub</a>.</p>"
    )


def not_found() -> str:
    return head(
        "Page not found",
        'There is no page at this address. <a href="/">Go to the overview</a>.',
    )


def build(results: Results, reading: dict[str, Any]) -> dict[str, str]:
    """Every page of the site, by file name."""
    return {
        "index.html": shell("index.html", "Overview", overview(results)),
        "example.html": shell(
            "example.html",
            "Worked example",
            example(reading),
            tag='<span class="tag synthetic">SYNTHETIC</span>',
        ),
        "results.html": shell("results.html", "Results", results_page(results)),
        "method.html": shell("method.html", "Method and data", method(results)),
        "404.html": shell("404.html", "Page not found", not_found(), root="/"),
    }
