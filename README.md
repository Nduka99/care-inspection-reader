# Care inspection reader

Reads the public inspection reports that the Care Quality Commission (CQC) publishes for home care
agencies in England, and finds the safety concerns they describe. Every finding quotes the exact
words it rests on, and the quote is checked in code. The findings are then compared with the
inspectors' own scores for each part of the "Safe" key question (1 = significant shortfalls to
4 = an exceptional standard).

The point is to test a text-extraction method on **real writing by real people**: inspectors'
reports, which quote the people who use the services and their relatives. No report text, provider
name or location name is stored in this repository. A fetch command rebuilds the data from CQC's
website, and results are reported in aggregate.

It is the companion of [Home-care intelligence](https://github.com/Nduka99/homecare_intelligence),
which uses the same method on carers' notes. Those notes are synthetic, so they cannot show how the
method does on real writing; these reports can.

Status: finished. The results are also published as a small website:
[reader.ndukanwagbo.com](https://reader.ndukanwagbo.com).

## Results

Test set, run once with nothing tuned on it: 207 reports, 1,554 scored sections. One section is
one Safe quality statement in one report. A section counts as **flagged** when the model gives at
least one finding whose quote is really in that section. Intervals are Wilson 95%.

| Measure | Result | 95% interval |
|---|---|---|
| **Sections scored 1 that were flagged** (the headline) | **274/274, 100%** | 98.6–100% |
| Sections scored 1 or 2 that were flagged | 713/723, 98.6% | 97.5–99.2% |
| Sections scored 3 ("a good standard") that were flagged | 67/782, 8.6% | 6.8–10.7% |
| Sections scored 4 ("exceptional") that were flagged | 0/49, 0% | 0–7.3% |
| Flagged shortfalls with a finding in the section's own statement | 684/713, 95.9% | 94.2–97.2% |
| Findings dropped because the quote was not in the text | 78/3,610, 2.2% | 1.7–2.7% |
| Sections the model could not answer | 0 | |

Flagging every section would also find 100% of the shortfalls, so the useful part is the gap:
every section scored 1 was flagged, against 8.6% of sections scored 3 and none scored 4.

**More findings go with worse scores.** A section scored 1 or 2 has more findings than one scored
3 or 4 98.5% of the time (AUROC 0.985, interval 0.979 to 0.991, ties counted half), and Kendall's
tau-b between findings and severity is 0.803 (0.783 to 0.823). The intervals come from a bootstrap
that resamples whole reports, 2,000 times. With the scores shuffled among the sections, the same
measures fall to 0.494 and −0.001, as they should when there is nothing to find.

**What a flag on a section scored 3 is.** A seeded sample of 20 of the 67 was read by hand:

- 13 are a real minor issue that the inspector noted and accepted;
- 5 are misreads, where a neutral or good statement was read as a shortfall, usually because of
  negative wording (a service that does not offer a task, or people who had no concerns to raise);
- 1 is an old problem quoted as if it were current;
- 1 is unclear.

**By statement** (test):

| Safe quality statement | Scored 1–2, flagged | Scored 3, flagged | Own-statement finding |
|---|---|---|---|
| Learning culture | 102/104 | 2/79 | 100/102 |
| Safe systems, pathways and transitions | 70/70 | 13/105 | 70/70 |
| Safeguarding | 88/89 | 8/112 | 75/88 |
| Involving people to manage risks | 118/118 | 4/75 | 108/118 |
| Safe environments | 66/67 | 9/116 | 66/66 |
| Safe and effective staffing | 115/118 | 9/77 | 115/115 |
| Infection prevention and control | 42/44 | 12/137 | 41/42 |
| Medicines optimisation | 112/113 | 10/81 | 109/112 |

Of the 29 flagged shortfalls with no finding in their own statement, 23 are in Safeguarding or
Involving people to manage risks: the shortfall was filed under a neighbouring statement such as
staffing. The section is still flagged.

## The model choice, and what it cost

Two local models with about 4 billion parameters each were compared with the same prompt:
Qwen3.5-4B and Gemma 4 E4B. The rule for choosing was written down before either ran, and used
the dev set only:

1. the higher share of sections scored 1 or 2 flagged;
2. if the two are within two sections of each other, the lower share of sections scored 3 flagged;
3. then the higher share of sections scored 1 flagged.

On dev, Gemma flagged 364/367 sections scored 1 or 2 and Qwen 363/367, which is within two. The
second rule decided: Qwen flagged 37/401 sections scored 3 (9.2%) against Gemma's 91/401 (22.7%).

Gemma was also run once on test, so the cost of the choice is measured, not guessed:

| On test | Qwen3.5-4B (chosen) | Gemma 4 E4B |
|---|---|---|
| Sections scored 1 flagged | 274/274 | 274/274 |
| Sections scored 1 or 2 flagged | 713/723 | 720/723 |
| Sections scored 3 flagged | 67/782, 8.6% | 136/782, 17.4% |
| Sections scored 4 flagged | 0/49 | 10/49 |

Comparing the two models section by section, Gemma caught 7 shortfall sections that Qwen missed,
and Qwen caught none that Gemma missed (exact two-sided sign test, p = 0.016). Read by hand, each
of the 7 states its shortfall in words, usually in one sentence inside a mostly positive section.
In return, Qwen flags half as many sections scored 3 and none scored 4. Both models missed the
same 3 shortfall sections, and read by hand, their text describes no shortfall: the score rests on
evidence the page does not show.

## How it works

1. **Sample.** From CQC's care directory with ratings, the home care agencies whose Safe rating was
   published from 1 January 2024, when CQC began scoring each quality statement. Score 1 is rare in
   a random sample, so agencies were drawn by Safe rating: every Inadequate (54) and Outstanding
   (17) agency, and seeded random samples of 160 Requires improvement and 100 Good. Of these 331,
   313 had a Safe page with scored statements and text (49, 152, 95 and 17).
2. **Split by provider.** The **dev** set is for design choices; the **test** set is scored once,
   at the end. One provider's agencies share policies and often wording, so about 30% of
   providers go to dev and 70% to test, by a hash of the provider ID. Providers whose reports were
   read while designing the parser go to dev. Dev holds 106 reports (795 sections) and test 207
   (1,554). Every parsed report was frozen by SHA-256 before any model ran.
3. **Leak guard.** The model reads only a section's paragraphs. It never sees the statement's name,
   the score, the rating banner or the overview, which states the rating and any breaches. The
   guard works on the page's HTML structure, not on words.
4. **Carried-over sections are left out.** When CQC did not assess a statement again, its text says
   so and its score comes from the previous rating, so the score says nothing about the text. The
   first scoring counted these sections; reading a sample of flags found them. 102 test sections and
   51 dev sections are left out, and the model choice was made again on the corrected dev scores
   (Gemma had led only because it flagged these placeholders).
5. **One call per section.** Each section is read on its own, with a cap of 8 findings. An early
   design read a whole report at once, and long reports used up the cap before their last sections.
6. **Findings.** Each finding has a category (one of the eight Safe quality statements), the exact
   words that state it and a one-sentence reason. llama.cpp's server holds the reply to a JSON
   schema, and the code checks it again. Each quote is looked up in the section's text: a finding
   whose quote is not there is dropped and counted, never repaired.
7. **Untrusted text.** Report text reaches the model as a JSON string, so nothing written in it can
   end the data field and pose as an instruction.
8. **Models.** Qwen3.5-4B and Gemma 4 E4B (Apache-2.0), as Q4_K_M GGUF files pinned by SHA-256 in
   `models.json`, served by llama.cpp's `llama-server` on one laptop GPU with 8 GB, at temperature 0.

## A worked example (SYNTHETIC)

[`site/example-page.html`](site/example-page.html) is an invented Safe page in CQC's layout: five
sections from a significant shortfall (score 1) to an exceptional standard (score 4). It describes
no real service. [`site/example-reading.json`](site/example-reading.json) is the chosen model's one
reading of it, kept as it came:

- the sections scored 1 and 2 are each flagged, and no quote was dropped;
- the section scored 3 is flagged for the one minor issue the inspector accepted;
- the section scored 4 has no findings;
- the shortfall about a moving plan is filed under staffing rather than its own statement, and one
  of the three medicines findings is filed under learning culture.

## How it is checked

`scripts/check.py` runs the formatter, linter, type checker and tests. Every protection has a test
that carries out the attack and passes only when the attack fails, and a twin test (named
`test_sabotage_*`) that switches the protection off and shows the attack then succeeds, which
proves the first test can fail:

- a made-up quote is dropped;
- no statement name, score, banner or overview text reaches the model;
- text that tries to close its data field stays inside it;
- no provider is in both dev and test;
- a path that robots.txt disallows is never fetched;
- the publish scan finds a planted CQC ID, the name of a sampled service, or any run of 8 words
  from a cached report (a run found in the reports of 5 or more providers is CQC's stock wording
  and is allowed);
- the public results file refuses any key outside its allow-list, so no per-report field can enter
  it, and a number that differs from the runs is caught.

Two checks need the fetched reports, which are not in this repository, so they run only on the
author's machine: the publish scan against every cached report, and
`inspection-reader results --check`, which rebuilds every number in `site/results.json` from the
model runs.

The results site is built from `site/` by a GitHub Actions workflow and published with GitHub
Pages. It has no scripts, and its own security policy allows nothing from another site. Two more
checks cover it: `scripts/ui_check.py _site` runs accessibility checks (axe, reflow, text spacing,
forced colours) in Chromium, Firefox and WebKit and attacks the page's security policy, and
`scripts/site_check.py https://reader.ndukanwagbo.com` checks the live site from outside, including
the publish scan on the pages as served.

## Limits

- Inspectors' prose is not daily care notes. It is written for the public, by trained people.
- The scores rest on more evidence than the text shows. Some shortfalls cannot be found from the
  page.
- A flag is a screen, not a grade: it says nothing about how serious the finding is.
- The sample is drawn by rating, so its mix of scores is not England's. Results are reported for
  each score for that reason.
- One prompt, written before the runs and not tuned on this data. Two models were compared on dev
  only, and each ran once on test, at temperature 0; run-to-run variation was not measured.

## Run it

Needs [uv](https://docs.astral.sh/uv/).

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run every check | `uv run python scripts/check.py` |
| Read one saved Safe page with a local model | `uv run inspection-reader read --model qwen3.5-4b page.html` |
| Read the synthetic example | `uv run inspection-reader read --model qwen3.5-4b site/example-page.html` |
| Build the results site into `_site/` | `uv run inspection-reader site --out _site` |

A read needs llama.cpp's `llama-server` on `PATH` (or its path in `LLAMA_SERVER`) and the model
file in `models/`, matching its size and SHA-256 in `models.json`. The synthetic page's five
sections took 15 seconds on an 8 GB laptop GPU, loading the model included.

**Rebuild the study.** The data is not in this repository. Download CQC's care directory (CSV) and
care directory with ratings (ODS) from CQC's website into `data/raw/directory/` and
`data/raw/ratings/`. Write `{"providers": []}` to `data/seen.json` (it lists the providers whose
reports you read by hand before the run; they go to dev). Then:

| Step | Command |
|---|---|
| Choose agencies and split them | `uv run inspection-reader sample` |
| Fetch and parse their Safe pages (one request every 3 s, robots.txt respected) | `uv run inspection-reader fetch` |
| Freeze both sets by SHA-256 | `uv run inspection-reader register` |
| Read every section and score it, for each model in `models.json` and each split | `uv run inspection-reader extract --model qwen3.5-4b --split dev`, then `evaluate` and `analyse` with the same options |
| Write the public aggregates, or check them | `uv run inspection-reader results`, `uv run inspection-reader results --check` |

CQC updates its files and pages, so a rebuild on later files gives a different sample.

## Data

Contains CQC information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
This project is not connected with or endorsed by CQC.

- Sources: CQC's care directory of 4 November 2026 and care directory with ratings of 2 November
  2026, and the Safe page of each sampled agency's latest report with scored statements, fetched
  on 4 November 2026.
- No report text, provider name or location name is stored in this repository or on its site.
  Results are aggregates; the only report shown in full is the synthetic example.

## Licence

MIT. See `LICENSE`.
