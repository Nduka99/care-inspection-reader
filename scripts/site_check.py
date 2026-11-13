"""Checks the published results site from outside, as a visitor reaches it. Run on the author's
laptop after each deployment:

    uv run python scripts/site_check.py https://reader.ndukanwagbo.com

1. Every page answers 200 over HTTPS, the plain-HTTP address redirects to HTTPS, and a missing
   address gets the not-found page with status 404.
2. Every page carries the site's Content Security Policy before anything it loads, has no
   script, loads nothing from another site, and every link between pages resolves.
3. No CQC ID, sampled service's name or run of report text is on any page: the publishing scan,
   run on the fetched pages against the cached reports in the git-ignored `data/` folder, so
   only the machine that holds them can run it.

A sabotaged copy of the first page (policy removed, an image from another site, a planted CQC
ID) must be caught by checks 2 and 3, or a clean run proves nothing. Exits 1 on any failure.
"""

import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from inspection_reader import leaks
from inspection_reader.site import PAGES, POLICY

AGENT = "care-inspection-reader-site-check"
POLICY_META = f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">'
MISSING = "no-such-page"
# A CQC-format ID for the sabotaged copy, built when the script runs so this file holds none and
# passes the same publishing scan.
PLANTED_ID = "1-" + "9" * 9


class Addresses(HTMLParser):
    """The pages a page links to, the files it loads and how many scripts it has."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.loads: list[str] = []
        self.scripts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "script":
            self.scripts += 1
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        elif tag == "link" and values.get("href"):
            self.loads.append(values["href"])
        elif values.get("src"):
            self.loads.append(values["src"])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reports a redirect instead of following it."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def fetch(url: str, follow: bool = True) -> tuple[int, str, str]:
    """The status, the Location header and the body of one request."""
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, "", response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, error.headers.get("Location", ""), body


def page_problems(url: str, html: str) -> tuple[list[str], set[str]]:
    """What is wrong with one page, and the addresses of the pages it links to on this site."""
    problems = []
    load_at = html.find("<link")
    if POLICY_META not in html or (load_at != -1 and html.index(POLICY_META) > load_at):
        problems.append(f"{url}: the policy is missing or comes after a file the page loads")
    found = Addresses()
    found.feed(html)
    if found.scripts:
        problems.append(f"{url}: {found.scripts} script(s)")
    host = urlsplit(url).netloc
    for load in found.loads:
        if urlsplit(urljoin(url, load)).netloc != host:
            problems.append(f"{url}: loads {load} from another site")
    internal = set()
    for link in found.links:
        address = urljoin(url, link).split("#")[0]
        if urlsplit(address).netloc == host:
            internal.add(address)
    return problems, internal


def control(url: str, html: str, names: list[str], runs: set[str]) -> list[str]:
    """The sabotaged copy: each planted fault must be reported."""
    sabotaged = html.replace(POLICY_META, "").replace(
        "</main>", f'<img src="https://example.com/x.png" alt=""><p>{PLANTED_ID}</p></main>'
    )
    problems, _ = page_problems(url, sabotaged)
    failures = []
    if not any("policy" in problem for problem in problems):
        failures.append("control: the missing policy was not caught")
    if not any("another site" in problem for problem in problems):
        failures.append("control: the image from another site was not caught")
    if not leaks.findings({url: sabotaged}, names, runs):
        failures.append("control: the planted CQC ID was not caught")
    return failures


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: site_check.py https://host")
        return 2
    base = sys.argv[1].rstrip("/")
    host = urlsplit(base).netloc
    failures = []

    pages = {}
    for name in [""] + [file for file, _ in PAGES]:
        url = f"{base}/{name}"
        status, _, html = fetch(url)
        if status != 200:
            failures.append(f"{url}: status {status}")
        pages[url] = html

    status, location, _ = fetch(f"http://{host}/", follow=False)
    if status not in (301, 308) or not location.startswith(f"https://{host}"):
        failures.append(f"plain http: status {status}, to {location!r}")

    status, _, html = fetch(f"{base}/{MISSING}")
    if status != 404 or "Page not found" not in html:
        failures.append(f"missing page: status {status}")

    internal = set()
    for url, html in pages.items():
        problems, links = page_problems(url, html)
        failures += problems
        internal |= links
    for link in sorted(internal):
        status, _, _ = fetch(link)
        if status != 200:
            failures.append(f"link {link}: status {status}")

    names, runs = leaks.load_watch_list(Path("data"))
    failures += leaks.findings(pages, names, runs)
    first_url, first_html = next(iter(pages.items()))
    failures += control(first_url, first_html, names, runs)

    print(f"{len(pages)} pages, {len(internal)} links between pages, {len(failures)} failures")
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
