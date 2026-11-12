"""Polite, cached fetching of CQC pages.

- robots.txt is read with this project's own user agent. CQC answers Python's default agent
  with 403, and urllib's robots parser then treats every path as disallowed.
- At most one request every `DELAY` seconds.
- Every page is cached in `pages/` with its SHA-256 in `manifest.json`, so a rerun reads the
  same bytes, and a cached page that changed is refused.
"""

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.robotparser import RobotFileParser

BASE = "https://www.cqc.org.uk"
AGENT = "care-inspection-reader/0.1 (non-commercial research; 1 request per 3 s)"
DELAY = 3.0
RETRY_WAITS = (15, 60, 180)


class Refused(Exception):
    """A page that must not be fetched or used."""


def download(url: str) -> bytes:
    """The page's bytes. A dropped connection or timeout is tried again after a longer wait
    each time (a long crawl met one TLS handshake timeout); an HTTP error status is not."""
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for wait in RETRY_WAITS:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data: bytes = response.read()
            return data
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(wait)
    with urllib.request.urlopen(request, timeout=60) as response:
        last: bytes = response.read()
    return last


def robots_rules(text: str) -> RobotFileParser:
    rules = RobotFileParser()
    rules.parse(text.splitlines())
    return rules


class Fetcher:
    def __init__(
        self,
        folder: Path,
        rules: RobotFileParser,
        get: Callable[[str], bytes] = download,
        delay: float = DELAY,
    ) -> None:
        self.pages = folder / "pages"
        self.pages.mkdir(parents=True, exist_ok=True)
        self.manifest_path = folder / "manifest.json"
        self.manifest: dict[str, dict[str, str]] = {}
        if self.manifest_path.exists():
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.rules = rules
        self.get = get
        self.delay = delay
        self.last = float("-inf")

    def page(self, path: str, name: str) -> str:
        """The page at `path` on CQC's site, from the cache when it is there."""
        cached = self.pages / name
        if cached.exists():
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() != self.manifest[name]["sha256"]:
                raise Refused(f"{name} changed since it was fetched")
            return data.decode("utf-8", errors="replace")
        url = BASE + path
        if not self.rules.can_fetch(AGENT, url):
            raise Refused(f"robots.txt disallows {url}")
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        data = self.get(url)
        self.last = time.monotonic()
        cached.write_bytes(data)
        self.manifest[name] = {"url": url, "sha256": hashlib.sha256(data).hexdigest()}
        text = json.dumps(self.manifest, indent=1, sort_keys=True) + "\n"
        self.manifest_path.write_text(text, encoding="utf-8", newline="\n")
        return data.decode("utf-8", errors="replace")
