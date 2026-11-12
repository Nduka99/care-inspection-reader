"""Which home care agencies to read, and the dev/test split.

Score 1 ("significant shortfalls") was missing from a random sample of 136 statements, so the
sample is drawn by Safe rating: every Inadequate and Outstanding agency, and seeded samples of
the rest. Only reports published from 2024 are used, when CQC's new approach with scored
quality statements began.

The split is by provider: one provider's agencies share policies and often inspectors' wording,
so a provider in both dev and test would leak dev's lessons into test.
"""

import hashlib
import random

SINCE = "2024-01-01"
SEED = 7
# None takes every agency with that rating.
PER_RATING: dict[str, int | None] = {
    "Inadequate": None,
    "Requires improvement": 160,
    "Good": 100,
    "Outstanding": None,
}
DEV_SHARE = 30  # percent of providers


def choose(records: list[dict[str, str]]) -> list[dict[str, str]]:
    chosen = []
    for rating, count in PER_RATING.items():
        pool = [r for r in records if r["rating"] == rating and r["published"] >= SINCE]
        pool.sort(key=lambda record: record["location"])
        random.Random(f"{SEED}-{rating}").shuffle(pool)
        chosen += pool if count is None else pool[:count]
    return sorted(chosen, key=lambda record: record["location"])


def split_of(provider: str, seen: set[str]) -> str:
    """ "dev" or "test" for a provider, fixed by a hash of its ID (stable across runs and
    machines, unlike Python's own `hash`). `seen` providers, whose report text was read by hand
    while designing the project, go to dev, so no test report has been seen."""
    if provider in seen:
        return "dev"
    bucket = int(hashlib.sha256(provider.encode()).hexdigest()[:8], 16) % 100
    return "dev" if bucket < DEV_SHARE else "test"
