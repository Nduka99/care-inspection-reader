"""The browser checks for the results site, run on the author's laptop with Playwright's
Chromium, Firefox and WebKit (Safari's engine) installed:

    uv run inspection-reader site --out _site
    uv run python scripts/ui_check.py _site

1. Accessibility: axe-core's WCAG 2.0, 2.1 and 2.2 A and AA rules on every page, at phone and
   desktop widths, in light and dark, in each engine. Then reflow at 320 and 390 px (no sideways
   scroll) and the WCAG text-spacing test at both (no text clipped). A positive control, a page
   made faint, with no language and too wide, must be reported in each engine, or a clean run
   proves nothing.
2. The page's own security policy, attacked: a copy of a page with an inline script, a script and
   an image from another site. No script may run and no request may leave. Sabotage: the same
   copy without its policy, where the attack must get through.
3. A visitor's walk in each engine, on a phone (touch) and a desktop: every page, every link
   between pages, back and forward, the details box, a mistyped and an extensionless address,
   the keyboard path from the skip link, and high-contrast mode (Chromium only: the others
   cannot emulate it). Console errors and requests to other sites are failures.

The folder is served as GitHub Pages serves it: an address without .html finds the page, and a
missing page gets 404.html with status 404. axe-core 4.13.0 (MPL-2.0) is in `tests/ui/axe.min.js`,
copied unchanged from its npm package and checked against its SHA-256 here; it is injected with
the policy bypassed, in its own browser context only. Screenshots go to `data/ui/` (git-ignored).
Exits 1 on any failure.
"""

import functools
import hashlib
import http.server
import sys
import threading
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Page,
    Playwright,
    sync_playwright,
)

AXE = Path("tests/ui/axe.min.js")
AXE_SHA256 = "c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
OUT = Path("data/ui")
ENGINES = ("chromium", "firefox", "webkit")
PAGES = {
    "index.html": "Overview",
    "example.html": "Worked example",
    "results.html": "Results",
    "method.html": "Method and data",
}
SIZES = {"phone": (390, 844), "desktop": (1280, 900)}
# Addresses the walk mistypes on purpose; the browser logs their 404 to the console.
MISSING = ("/reslts", "/old/folder/page")
# WCAG 2.2 success criterion 1.4.12: text must survive these spacings without loss.
TEXT_SPACING = (
    "* { line-height: 1.5 !important; letter-spacing: 0.12em !important;"
    " word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }"
)
ATTACK = (
    "<script>window.attacked = true</script>"
    '<script src="https://attacker.example/x.js"></script>'
    '<img src="https://attacker.example/x.png" alt="">'
)


class PagesLike(http.server.SimpleHTTPRequestHandler):
    """Serves a folder as GitHub Pages does."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def send_head(self) -> Any:
        path = Path(self.translate_path(self.path))
        if not path.exists() and path.with_suffix(".html").is_file():
            self.path = self.path.split("?")[0] + ".html"
        elif not path.exists():
            body = (Path(self.directory) / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().send_head()


def serve(folder: Path) -> tuple[str, http.server.ThreadingHTTPServer]:
    handler = functools.partial(PagesLike, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", server


def settled(page: Page) -> None:
    """Wait until the page change's cross-fade has finished, so a check sees one page."""
    page.wait_for_load_state("load")
    for _ in range(100):
        if page.evaluate("() => document.getAnimations().length") == 0:
            return
        page.wait_for_timeout(50)


# 1. Accessibility.


def axe(page: Page) -> list[str]:
    page.add_script_tag(path=str(AXE))
    found: list[str] = page.evaluate(
        "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}}))"
        ".violations.map(v => `${v.id} (${v.impact}): ${v.help} at "
        "${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join('; ')}`)",
        TAGS,
    )
    return found


def sideways(page: Page) -> list[str]:
    """Reflow, which axe does not test: the page must not scroll sideways."""
    extra: int = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    return [f"reflow: the page scrolls sideways by {extra} px"] if extra > 0 else []


def clipped(page: Page) -> list[str]:
    """Elements that hide part of their own content (screen-reader-only text excepted)."""
    found: list[str] = page.evaluate(
        "() => [...document.body.querySelectorAll('*')].filter(e => {"
        " const s = getComputedStyle(e);"
        " if (e.closest('.visually-hidden') || e instanceof SVGElement) return false;"
        " const hides = s.overflowX !== 'visible' || s.overflowY !== 'visible';"
        " const wider = e.scrollWidth > e.clientWidth + 1;"
        " return hides && (wider || e.scrollHeight > e.clientHeight + 1);"
        "}).map(e => `clipped: ${e.tagName.toLowerCase()}.${e.className}`)"
    )
    return found


def accessibility(browser: Browser, engine: str, base: str) -> list[str]:
    failures = []
    for size, (width, height) in SIZES.items():
        for scheme in ("light", "dark"):
            context = browser.new_context(
                bypass_csp=True,
                viewport={"width": width, "height": height},
                color_scheme=scheme,
            )
            page = context.new_page()
            for name in [*PAGES, "404.html"]:
                page.goto(f"{base}/{name}")
                settled(page)
                shot = OUT / f"{engine}-{name.removesuffix('.html')}-{size}-{scheme}.png"
                page.screenshot(path=str(shot), full_page=True)
                for problem in axe(page) + sideways(page):
                    failures.append(f"{engine} {name} {size} {scheme}: {problem}")
            context.close()
    for width in (320, 390):
        # The text-spacing style is injected, so the policy is bypassed here too.
        context = browser.new_context(bypass_csp=True, viewport={"width": width, "height": 640})
        page = context.new_page()
        for name in [*PAGES, "404.html"]:
            page.goto(f"{base}/{name}")
            settled(page)
            for problem in sideways(page):
                failures.append(f"{engine} {name} {width} px: {problem}")
            page.add_style_tag(content=TEXT_SPACING)
            for problem in sideways(page) + clipped(page):
                failures.append(f"{engine} {name} {width} px, text spacing: {problem}")
        context.close()
    return failures


CONTROL_EXPECTS = {"color-contrast", "html-has-lang", "reflow"}


def control(browser: Browser, engine: str, base: str) -> list[str]:
    """The positive control: the home page made faint, without its language and too wide."""
    context = browser.new_context(bypass_csp=True, viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(f"{base}/index.html")
    page.add_style_tag(
        content="body, body * { color: #c8c8c8 !important; } main::after { content: '';"
        " display: block; width: 40rem; height: 1px; }"
    )
    page.evaluate("() => document.documentElement.removeAttribute('lang')")
    found = {problem.split(" ")[0].rstrip(":") for problem in axe(page) + sideways(page)}
    context.close()
    missed = CONTROL_EXPECTS - found
    return [f"{engine} control: not reported {sorted(missed)}"] if missed else []


# 2. The page's security policy, attacked.


def attacked(browser: Browser, base: str, html: str) -> tuple[bool, list[str]]:
    """Open `html` at the site's own address; whether its script ran, and what left."""
    context = browser.new_context()
    page = context.new_page()
    outside: list[str] = []

    def route(request_route: Any) -> None:
        url = request_route.request.url
        if url == f"{base}/attacked.html":
            request_route.fulfill(status=200, content_type="text/html", body=html)
        elif url.startswith(base):
            request_route.continue_()
        else:
            outside.append(url)
            request_route.abort()

    page.route("**/*", route)
    page.goto(f"{base}/attacked.html")
    page.wait_for_timeout(300)
    ran = bool(page.evaluate("() => window.attacked === true"))
    context.close()
    return ran, outside


def policy_attack(browser: Browser, engine: str, base: str, folder: Path) -> list[str]:
    page = (folder / "index.html").read_text(encoding="utf-8")
    with_attack = page.replace("</main>", ATTACK + "</main>")
    failures = []
    ran, outside = attacked(browser, base, with_attack)
    if ran or outside:
        failures.append(f"{engine} policy: script ran={ran}, requests left={outside}")
    policy = next(line for line in page.splitlines() if "Content-Security-Policy" in line)
    ran, outside = attacked(browser, base, with_attack.replace(policy, ""))
    if not (ran and outside):
        failures.append(f"{engine} sabotage: without the policy the attack did not get through")
    return failures


# 3. A visitor's walk.


def console(message: ConsoleMessage, who: str, failures: list[str]) -> None:
    if not message.location.get("url", "").endswith(MISSING):
        failures.append(f"{who}: console {message.type}: {message.text}")


def watched(context: BrowserContext, base: str, who: str, failures: list[str]) -> Page:
    page = context.new_page()
    page.on("console", lambda m: console(m, who, failures))
    page.on("pageerror", lambda e: failures.append(f"{who}: page error: {e}"))

    def route(request_route: Any) -> None:
        if request_route.request.url.startswith(base):
            request_route.continue_()
        else:
            failures.append(f"{who}: a request left the site: {request_route.request.url}")
            request_route.abort()

    page.route("**/*", route)
    return page


def press_link(page: Page, link: Any, touch: bool) -> None:
    with page.expect_navigation(wait_until="load"):
        if touch:
            link.tap()
        else:
            link.click()
    settled(page)


def expect(failures: list[str], who: str, what: str, ok: bool) -> None:
    if not ok:
        failures.append(f"{who}: {what}")


def walk(browser: Browser, engine: str, base: str, size: str) -> list[str]:
    failures: list[str] = []
    who = f"{engine} {size}"
    width, height = SIZES[size]
    touch = size == "phone"
    options: dict[str, Any] = {"viewport": {"width": width, "height": height}}
    if touch:
        options["has_touch"] = True
        if engine == "chromium":
            options["is_mobile"] = True
    context = browser.new_context(**options)
    page = watched(context, base, who, failures)
    for name, label in PAGES.items():
        response = page.goto(f"{base}/{name}")
        settled(page)
        expect(failures, who, f"{name} answered", response is not None and response.ok)
        expect(failures, who, f"{name} has a heading", bool(page.locator("h1").inner_text()))
        current = page.locator('nav [aria-current="page"]').inner_text()
        expect(
            failures, who, f"{name} marks {label!r} as current, not {current!r}", current == label
        )
        hrefs = page.locator("a[href]").evaluate_all("as => as.map(a => a.getAttribute('href'))")
        for href in dict.fromkeys(hrefs):
            if href.startswith(("http:", "https:", "#")):
                continue
            page.goto(f"{base}/{name}")
            settled(page)
            press_link(page, page.locator(f'a[href="{href}"]').first, touch)
            heading = page.locator("h1").inner_text()
            expect(failures, who, f"{name} -> {href} opens a page", heading != "Page not found")
    page.goto(f"{base}/index.html")
    settled(page)
    press_link(page, page.get_by_role("navigation").get_by_role("link", name="Results"), touch)
    page.go_back(wait_until="load")
    expect(failures, who, "back returns to the overview", page.url.endswith("/index.html"))
    page.go_forward(wait_until="load")
    expect(failures, who, "forward returns to the results", page.url.endswith("/results.html"))
    page.goto(f"{base}/example.html")
    settled(page)
    summary = page.locator("summary")
    if touch:
        summary.tap()
    else:
        summary.click()
    is_open = page.locator("details").get_attribute("open") is not None
    expect(failures, who, "the run details open", is_open)
    response = page.goto(base + MISSING[0])
    expect(
        failures,
        who,
        "a mistyped address answers 404",
        response is not None and response.status == 404,
    )
    expect(
        failures,
        who,
        "it shows the not-found page",
        page.locator("h1").inner_text() == "Page not found",
    )
    page.goto(base + MISSING[1])
    styled = page.evaluate("() => getComputedStyle(document.body).display")
    expect(failures, who, "a deep missing address is styled", styled == "flex")
    press_link(page, page.get_by_role("link", name="Go to the overview"), touch)
    expect(failures, who, "the not-found link goes home", page.url == f"{base}/")
    page.goto(f"{base}/results")
    expect(
        failures,
        who,
        "an address without .html works",
        page.locator("h1").inner_text() == "Results",
    )
    if not touch and engine != "webkit":
        # WebKit, like Safari, skips links on Tab unless the reader turns that on.
        page.goto(f"{base}/index.html")
        page.keyboard.press("Tab")
        first = page.evaluate("() => document.activeElement.className")
        expect(failures, who, "Tab reaches the skip link first", first == "skip")
        page.keyboard.press("Enter")
        page.keyboard.press("Tab")
        inside = page.evaluate("() => !!document.activeElement.closest('main')")
        expect(failures, who, "after the skip link, Tab lands in the main content", inside)
    context.close()
    return failures


def forced_colours(browser: Browser, base: str) -> list[str]:
    """High-contrast mode drops backgrounds and shadows: the current page needs its outline."""
    context = browser.new_context(forced_colors="active", viewport={"width": 390, "height": 844})
    page = context.new_page()
    failures = []
    for name in PAGES:
        page.goto(f"{base}/{name}")
        style = page.locator('nav [aria-current="page"]').evaluate(
            "e => getComputedStyle(e).outlineStyle"
        )
        if style == "none":
            failures.append(f"forced colours {name}: the current page is not marked")
    page.goto(f"{base}/example.html")
    page.screenshot(path=str(OUT / "chromium-example-forced-colours.png"), full_page=True)
    context.close()
    return failures


def run(playwright: Playwright, folder: Path, base: str) -> list[str]:
    failures = []
    for engine in ENGINES:
        browser = getattr(playwright, engine).launch()
        found = control(browser, engine, base)
        found += accessibility(browser, engine, base)
        found += policy_attack(browser, engine, base, folder)
        found += walk(browser, engine, base, "phone") + walk(browser, engine, base, "desktop")
        if engine == "chromium":
            found += forced_colours(browser, base)
        print(f"{engine}: {len(found)} failures", flush=True)
        failures += found
        browser.close()
    return failures


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    if hashlib.sha256(AXE.read_bytes()).hexdigest() != AXE_SHA256:
        raise SystemExit(f"{AXE} differs from its pin")
    OUT.mkdir(parents=True, exist_ok=True)
    base, server = serve(folder)
    try:
        with sync_playwright() as playwright:
            failures = run(playwright, folder, base)
    finally:
        server.shutdown()
    for failure in failures:
        print(failure)
    print("all browser checks passed" if not failures else f"FAILED: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
