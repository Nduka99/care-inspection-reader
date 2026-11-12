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

Status: being built.

## Run it

Needs [uv](https://docs.astral.sh/uv/).

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run every check | `uv run python scripts/check.py` |

## Data

Contains CQC information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
This project is not connected with CQC.

## Licence

MIT. See `LICENSE`.
