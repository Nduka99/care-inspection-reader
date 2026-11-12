"""Command line: `inspection-reader sample | fetch | ...`, run from the project folder.

All data lives in the git-ignored `data/` folder:
- `data/raw/directory/` and `data/raw/ratings/`: the CQC files, downloaded by hand (one each);
- `data/raw/pages/` and `data/raw/manifest.json`: fetched pages and their SHA-256;
- `data/seen.json`: providers whose reports were read while designing the project;
- `data/sample.json`: the agencies chosen, with their split;
- `data/reports/<split>/<location>.json`: each report's parsed Safe sections.

`site/results.json` is public: aggregates only, rebuilt from the runs by `results`.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from inspection_reader import (
    analysis,
    evaluate,
    extract,
    fetch,
    models,
    parse,
    ratings,
    results,
    sample,
    sets,
)

DATA = Path("data")
RAW = DATA / "raw"
# Public: aggregates only, built from the private runs.
RESULTS = Path("site") / "results.json"
PORT = 8091
SPLITS = ("dev", "test")


def only_file(folder: Path) -> Path:
    files = sorted(path for path in folder.iterdir() if path.is_file())
    if len(files) != 1:
        raise SystemExit(f"{folder}: expected exactly one file, found {len(files)}")
    return files[0]


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def run_sample() -> None:
    homecare = ratings.homecare_locations(only_file(RAW / "directory"))
    records = ratings.safe_ratings(only_file(RAW / "ratings"), homecare)
    seen = set(json.loads((DATA / "seen.json").read_text(encoding="utf-8"))["providers"])
    chosen = sample.choose(records)
    for record in chosen:
        record["split"] = sample.split_of(record["provider"], seen)
    write_json(DATA / "sample.json", chosen)
    print(f"{len(records)} rated home care agencies; {len(chosen)} chosen")
    for split in ("dev", "test"):
        print(split, sum(1 for record in chosen if record["split"] == split))


def latest_scored_report(fetcher: fetch.Fetcher, location: str) -> dict[str, Any] | None:
    """The newest report whose Safe page has scored sections with text, or None."""
    listing = fetcher.page(f"/location/{location}/reports", f"{location}_reports.html")
    marker = f'href="/location/{location}/reports/'
    reports = []
    for piece in listing.split(marker)[1:]:
        report, _, rest = piece.partition("/")
        if rest.startswith('overall"') and report not in reports:
            reports.append(report)
    for report in reports:
        path = f"/location/{location}/reports/{report}/overall/safe"
        page = parse.parse(fetcher.page(path, f"{location}_{report}_safe.html"))
        if page["sections"]:
            return {"report": report, **page}
    return None


def run_fetch(limit: int) -> None:
    chosen = json.loads((DATA / "sample.json").read_text(encoding="utf-8"))
    robots = fetch.download(fetch.BASE + "/robots.txt").decode("utf-8")
    fetcher = fetch.Fetcher(RAW, fetch.robots_rules(robots))
    kept = 0
    for record in chosen[:limit]:
        target = DATA / "reports" / record["split"] / f"{record['location']}.json"
        if target.exists():
            kept += 1
            continue
        found = latest_scored_report(fetcher, record["location"])
        if found is None:
            print(record["location"], "no scored Safe text", flush=True)
            continue
        write_json(target, {**record, **found})
        kept += 1
        scores = [section["score"] for section in found["sections"]]
        print(record["location"], record["rating"], scores, flush=True)
    print(f"{kept} reports with scored Safe text")


def run_register() -> None:
    for split in SPLITS:
        count = len(list((sets.ROOT / split).glob("*.json")))
        sets.register(split, f"{count} parsed Safe pages ({split})", sets.ROOT, sets.REGISTRY)
        print(f"{split}: {count} reports registered")


def reports_of(split: str) -> list[dict[str, Any]]:
    folder = sets.require(split, sets.ROOT, sets.REGISTRY)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def run_header(model: str) -> dict[str, str]:
    """What a reading depends on: the model file and the prompt."""
    return {"model": model, "sha256": models.entry(model)["sha256"], "prompt": extract.PROMPT_HASH}


def run_read(model: str, page: Path, out: Path | None) -> None:
    """Read one saved Safe page: each section's findings beside the inspector's score."""
    parsed = parse.parse(page.read_text(encoding="utf-8"))
    texts = [parse.model_text(section) for section in parsed["sections"]]
    # Its own log: a read must never overwrite the server log of an extraction run.
    with models.served(model, PORT, DATA / "logs" / f"read-{model}.log") as url:
        result = extract.extract(url, texts)
    sections = []
    for index, section in enumerate(parsed["sections"]):
        findings = [f for f in result["findings"] if f["section"] == index]
        sections.append({**section, "findings": findings})
    reading = {
        "header": run_header(model),
        "sections": sections,
        "dropped": result["dropped"],
        "error": result.get("error", []),
    }
    if out is None:
        print(json.dumps(reading, indent=1, ensure_ascii=False))
    else:
        write_json(out, reading)


def run_extract(model: str, split: str) -> None:
    header = run_header(model)
    reports = reports_of(split)
    out = DATA / "runs" / split / f"{model}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists() and read_jsonl(out)[:1] == [{"header": header}]:
        done = {record["location"] for record in read_jsonl(out)[1:]}
    else:
        out.write_text(json.dumps({"header": header}, sort_keys=True) + "\n", encoding="utf-8")
    with models.served(model, PORT, DATA / "logs" / f"{model}.log") as url:
        for report in reports:
            if report["location"] in done:
                continue
            texts = [parse.model_text(section) for section in report["sections"]]
            result = extract.extract(url, texts)
            append_jsonl(out, {"location": report["location"], **result})
            print(split, report["location"], len(result["findings"]), "findings", flush=True)


def run_evaluate(model: str, split: str) -> None:
    reports = reports_of(split)
    records = read_jsonl(DATA / "runs" / split / f"{model}.jsonl")
    runs = {record["location"]: record for record in records[1:]}
    result = {"split": split, "header": records[0]["header"], **evaluate.score(reports, runs)}
    write_json(DATA / "scores" / f"{split}--{model}.json", result)
    print(f"{split} ({result['reports']} reports, {result['sections']} sections), {model}")
    for key, value in result.items():
        if isinstance(value, dict) and "rate" in value:
            print(f"  {key:25} {value['found']:4}/{value['total']:<4} {value['rate']:.2f} "
                  f"({value['low']:.2f}-{value['high']:.2f})")  # fmt: skip
    print(
        f"  errors {len(result['errors'])}; missed score-1 sections {len(result['missed_score_1'])}"
    )


def run_analyse(model: str, split: str) -> None:
    """The analyses in `analysis.py`, whose rules were written down before computing them."""
    reports = reports_of(split)
    records = read_jsonl(DATA / "runs" / split / f"{model}.jsonl")
    runs = {record["location"]: record for record in records[1:]}
    sections = evaluate.scored_sections(reports, runs)
    published = {report["location"]: report["published"] for report in reports}
    result = {
        "split": split,
        "header": records[0]["header"],
        "grading": analysis.grading(sections),
        "shuffled_control": analysis.grading(analysis.shuffled(sections)),
        "by_topic": analysis.by_topic(sections),
        "memory": analysis.memory(sections, published),
    }
    write_json(DATA / "scores" / f"{split}--{model}--analysis.json", result)
    print(f"{split}, {model}")
    for kind in ("grading", "shuffled_control"):
        for key, value in result[kind].items():
            print(f"  {kind:16} {key:26} {value['value']:.3f} {value['interval']}")
    for statement, measures in result["by_topic"].items():
        recall = measures["recall_score_2_or_below"]
        flags = measures["flag_rate_score_3"]
        print(
            f"  {statement:40} recall<=2 {recall['found']}/{recall['total']}  "
            f"flag@3 {flags['found']}/{flags['total']}"
        )
    print(f"  memory {result['memory']}")


def runs_of(split: str, model: str) -> dict[str, dict[str, Any]]:
    records = read_jsonl(DATA / "runs" / split / f"{model}.jsonl")
    return {record["location"]: record for record in records[1:]}


def run_results(check: bool) -> None:
    """Write the public aggregates, or (--check) rebuild them and compare with the file."""
    sampled = json.loads((DATA / "sample.json").read_text(encoding="utf-8"))
    reports = {split: reports_of(split) for split in SPLITS}
    runs = {}
    for split in SPLITS:
        runs[split] = {model: runs_of(split, model) for model in (results.CHOSEN, results.COMPARED)}
    fresh = results.build(sampled, reports, runs)
    problems = results.problems(fresh)
    if check:
        committed = json.loads(RESULTS.read_text(encoding="utf-8"))
        problems = results.problems(committed) + results.differences(committed, fresh)
    for problem in problems:
        print(problem)
    if problems:
        raise SystemExit(f"{len(problems)} problems; {RESULTS} not trusted")
    if check:
        print(f"{RESULTS}: every number matches the runs")
    else:
        write_json(RESULTS, fresh)
        print(f"wrote {RESULTS}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="inspection-reader")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sample", help="choose agencies by Safe rating and split by provider")
    fetch_command = commands.add_parser(
        "fetch", help="fetch and parse the chosen agencies' Safe pages"
    )
    fetch_command.add_argument("--limit", type=int, default=10_000)
    commands.add_parser("register", help="record the SHA-256 of every parsed report")
    for name in ("extract", "evaluate", "analyse"):
        command = commands.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--split", required=True, choices=SPLITS)
    read = commands.add_parser("read", help="read one saved Safe page with a local model")
    read.add_argument("--model", required=True)
    read.add_argument("--out", type=Path, help="write the reading here instead of printing it")
    read.add_argument("page", type=Path, help="a Safe page saved from CQC's website")
    results_command = commands.add_parser("results", help="write the public aggregates")
    results_command.add_argument(
        "--check", action="store_true", help="rebuild them from the runs and compare with the file"
    )
    args = parser.parse_args(argv)
    if args.command == "read":
        run_read(args.model, args.page, args.out)
    elif args.command == "results":
        run_results(args.check)
    elif args.command == "sample":
        run_sample()
    elif args.command == "fetch":
        run_fetch(args.limit)
    elif args.command == "register":
        run_register()
    elif args.command == "extract":
        run_extract(args.model, args.split)
    elif args.command == "analyse":
        run_analyse(args.model, args.split)
    else:
        run_evaluate(args.model, args.split)
