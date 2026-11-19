# Automated Job Discovery Pipeline

Collects job postings from multiple boards, deduplicates them into one record
per real-world role, filters them against the operator's title and experience
criteria, scores what survives against a CV using a locally hosted model, and
presents the ranked results in a local web interface for triage.

**No data leaves the machine, and there is no recurring cost.** Everything runs
on the operator's own hardware: PostgreSQL in a container, scoring through
[Ollama](https://ollama.com/) on the host, and a FastAPI interface bound to
localhost. There is no SaaS account, no API key, and no third party holding the
CV or the search history.

---

## The problem

Searching several job boards by hand produces the same posting several times
over, in slightly different words. The same role appears as *Senior Data
Engineer* on one board and *Sr. Data Engineer (Remote)* on another; the same
city appears as `Cairo, Egypt` and as `القاهرة, C, EG`. Deduplicating that by
eye is the tedious part, and it is the part that hides postings — two variants
of one role look like two opportunities, while a genuinely different role gets
skimmed past because it looks like one already seen.

This pipeline does the collection and the deduplication mechanically, then
ranks what survives against an actual CV so the reading order is worth
something.

### The governing constraint

Deduplication is asymmetric, and the whole design turns on it:

> **A false merge conceals a posting. A false split merely repeats one.**

Missing a job because two distinct roles were collapsed into one record is a
real loss. Seeing the same role twice is an annoyance. Every fingerprinting
rule is therefore biased toward *splitting* when uncertain, and the test suite
asserts non-merging at least as hard as it asserts merging. Contributors are
expected to preserve this — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Status

| Stage | What it does | State |
|---|---|---|
| 1 — Collect | Query boards via JobSpy, land raw postings | **Implemented** |
| 2 — Normalise | Fingerprint and deduplicate into one record per role | **Implemented** |
| Filter | Judge each posting against title and experience criteria; record a verdict | **Implemented** |
| 3 — Score | Score the postings the filter did not withhold against the CV via Ollama | Specified, not built |
| 4 — Publish | Mark above-threshold postings for review | Specified, not built |
| Triage UI | FastAPI interface for reviewing and acting on results | **Implemented** |

The filter is the title pre-filter the design placed at the front of stage 3
(D6), pulled out into its own step so that it can run, and be re-applied, before
scoring exists. It sits between stages 2 and 3 and does not renumber them
([ADR-0016](Docs/ADRs/0016-collect-stage-filter-verdicts.md)).

Stages 3 and 4 are fully specified in the design record and the SRS; the CLI
subcommands exist and report that they are unimplemented. Documents describing
unbuilt behaviour are marked **(planned)**.

---

## Architecture

Four stages run in order, with the filter between the second and third. Each is
independently invocable against stored data, and each is idempotent — re-running
against the same input converges on the same state.

```mermaid
flowchart TD
    boards(["Job boards<br>Indeed, LinkedIn, ..."])
    ollama(["Ollama<br>local model, on the host"])

    collect["1 — collect<br>query boards, land raw rows"]
    normalise["2 — normalise<br>fingerprint, dedupe"]
    filt["filter<br>title and experience verdicts"]
    score["3 — score (planned)<br>CV match"]
    publish["4 — publish (planned)<br>flag above-threshold postings"]
    ui["Triage UI<br>FastAPI + Jinja2"]

    raw[("raw_postings")]
    postings[("postings, employers<br>one row per real-world role")]

    boards -- JobSpy --> collect
    collect --> raw
    raw --> normalise
    normalise --> postings
    postings --> filt
    filt -- "verdict columns" --> postings
    postings -- "postings the filter did not withhold" --> score
    score -. "prompt, then score" .-> ollama
    score -- "postings.score" --> publish
    publish -- "postings.published" --> ui
    ui -- "triage status only" --> postings

    classDef planned stroke-dasharray: 5 5
    class score,publish planned
```

The filter and stages 3 and 4 write columns on `postings` rather than tables of
their own, so re-applying one overwrites rather than accumulates. The filter's
columns are `title_filter_passed` and `experience_filter_passed`; stages 3 and 4
will write `score`, `scored_by_model` and `published`. Each run records its
per-stage counts in `runs`, including how many postings the filter passed and
rejected, and that is what `status` reads back.

### The filter

The filter judges every posting a run surfaced against two criteria
([ADR-0016](Docs/ADRs/0016-collect-stage-filter-verdicts.md)):

- **Title.** Include and exclude patterns applied to the job title. Global
  patterns are set at `/settings` and bind every posting. Each search profile
  can add its own at `/profiles`; these add to the global patterns and cannot
  loosen them ([ADR-0018](Docs/ADRs/0018-per-profile-title-rules.md)).
- **Experience.** The level recorded on the search profiles that surfaced the
  posting, compared against the board's declared seniority. Where the board
  declares none, the title is read for a seniority word instead
  ([ADR-0017](Docs/ADRs/0017-board-seniority-label-reliability.md),
  [ADR-0020](Docs/ADRs/0020-seniority-for-boards-without-a-label.md)).

Rejected postings are **withheld, not deleted.** A verdict is stored on the
posting and applied when the posting is read. A rejected posting drops out of
the queue only while it is untriaged. Anything already shortlisted or applied to
stays where it is, and the withheld set can be viewed at
`/postings?verdict=rejected` along with the criterion that rejected each one. The
filter fails open: an empty pattern, a blank experience level or a posting of
unknown seniority rejects nothing. When the criteria change,
`filter --all` re-applies them to every stored posting without contacting a
board, and running it again under the same criteria writes nothing.

### Dependency direction

This is strict, load-bearing, and enforced in review. An arrow means *imports*:

```mermaid
flowchart TD
    subgraph app["app.config — depends on nothing; everything below rests on it"]
        web["web/<br>reads the DB, writes triage status"]
        pipeline["pipeline/<br>the only layer that persists"]
        services["services/<br>settings, profiles, blacklist,<br>triage, queries, reports"]
        db["db/<br>models, session,<br>read-time seams"]
        collect["collect/<br>pure transform"]
        normalise["normalise/<br>pure transform"]
        filters["filters/<br>pure criteria"]
    end

    pipeline --> collect
    pipeline --> normalise
    pipeline --> filters
    pipeline --> services
    pipeline --> db
    web --> services
    web --> db
    services --> db
    services --> filters
    db --> filters
```

Note what is absent: nothing points *into* `collect/` or `normalise/` except
`pipeline/`, and none of `collect/`, `normalise/` or `filters/` points at `db/`.
`filters/` is pure like those two, but more than one layer imports it.
`pipeline/` evaluates the criteria to record verdicts.
`services/` evaluates them so the interface can explain why a posting was
rejected. `db/attribution.py` uses them to resolve the profiles that surfaced a
posting.

Every module in the box also imports `config.py` directly — that fan-in is
omitted above since it would just be an edge from every box to one, and it
adds nothing past the label. The one exception is `config.py` itself:
`RunConfig.resolve()` imports `services/settings.py` inside the function body
(not at module scope) so it can read the database before falling back to
environment or code default (ADR-0005). The local import is what keeps that
from being a real cycle — it's deliberate, and the comment at
[config.py:126](app/src/app/config.py#L126) says so.

- **`config.py` depends on nothing; everything depends on it.** Never read
  `os.environ` directly anywhere else — add a field to `Settings` instead.
- **`collect/`, `normalise/` and `filters/` know nothing of the database.**
  They are pure transforms, testable without any infrastructure. This is what
  makes the fingerprint and criteria logic trivially testable, and it is lost
  the moment one of them imports a session.
- **`pipeline/` is the only layer that persists.** It composes `collect`,
  `normalise` and `filters` and writes the results. `pipeline/filter_stage.py`
  is the only writer of a filter verdict.
- **`web/` reads the database and never writes pipeline data** — only triage
  status.

If a change requires violating one of these, that is a design discussion (and
probably an ADR), not a refactor to slip into a feature PR.

---

## Repository structure

The Python project is nested under `app/`; the repository root holds
documentation and specifications.

```
Automatic-Job-search/
├── README.md                  This file — the front door
├── CONTRIBUTING.md            Conventions, review rules, the ADR and spec process
├── SECURITY.md                Reporting, and this project's actual attack surface
├── NOTICE.md                  Scraping, terms of service, and personal data
├── .trufflehog/               Secret-scanning config and path filters
├── .github/workflows/         CI and secret scanning
│
├── Docs/                      Design record, SRS, architecture, guides, ADRs
│   └── README.md              ← start here for the reasoning behind a decision
│
├── specs/                     Per-feature specifications (spec-kit numbering)
│   └── NNN-slug/              spec.md, plan.md, tasks.md, research.md
│
└── app/                       ★ The Python project — run commands from here
    ├── pyproject.toml         Dependencies and tool config (uv)
    ├── docker-compose.yml     postgres, migrate, web, scheduler
    ├── migrations/            Alembic
    ├── src/app/
    │   ├── __main__.py        Typer CLI — the single entry point
    │   ├── config.py          Typed settings; the one source of truth
    │   ├── collect/           Stage 1 — JobSpy
    │   ├── normalise/         Fingerprinting (country, employer, title)
    │   ├── filters/           Title and experience criteria (pure)
    │   ├── pipeline/          Orchestration + persistence, incl. filter_stage.py
    │   ├── db/                SQLAlchemy models, session, read-time seams
    │   ├── services/          Shared service-layer logic
    │   └── web/               FastAPI triage interface
    └── tests/                 pytest — runs with no Docker and no services
```

**`Docs/` is reasoning; `specs/` is planned work.** `Docs/` holds durable
records — why the system is shaped as it is, what it must do, and the ADRs that
fix individual decisions. `specs/NNN-slug/` holds the working specification for
one feature under development, and its directory name matches the branch name.

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/), Docker, and — for stage 3 — Ollama on
the host. Python 3.12 is pinned by `app/.python-version` and installed by uv.

**All commands run from `app/`.**

```bash
cd app
cp .env.example .env          # then edit; see the table in the deployment guide
docker compose up -d          # postgres, migrate, web, scheduler
```

Then open <http://localhost:8000>.

For development against a host-side environment:

```bash
cd app
uv sync                          # create .venv from the locked graph
docker compose up -d postgres    # just the database
uv run python -m app web --reload
```

### Everyday commands

```bash
uv run pytest                       # full suite — no Docker required
uv run pytest tests/test_fingerprint.py
uv run ruff check src tests         # lint
uv run ruff format src tests        # format
uv run python -m app --help         # every stage is a subcommand
```

The CLI is the single entry point, so any stage can run independently against
stored data:

| Command | Does |
|---|---|
| `collect` | Stage 1 — collect and land raw postings |
| `normalise [--run-id N]` | Stage 2 — fingerprint and deduplicate |
| `filter [--run-id N] [--all] [--dry-run]` | Record title and experience verdicts for one run (default: the latest). `--all` re-applies the criteria to every posting; `--dry-run` reports what would change and writes nothing |
| `score` | Stage 3 — model scoring of the postings the filter did not withhold *(planned)* |
| `publish` | Stage 4 — mark above-threshold published *(planned)* |
| `run-all` | Every stage in order, filter included, recording per-stage counts |
| `serve` | Run the scheduler in the foreground |
| `web` | Serve the triage interface |
| `status` | Recent runs and their per-stage counts, including filter passed/rejected |
| `config` | Print effective configuration, secrets masked |

---

## Configuration

Configuration resolves in the order **database → environment/`.env` → code
default** (ADR-0005). The operational settings — searches, thresholds, filters,
delays — are edited in the web UI and stored in the database; the values in
`.env` seed the first migration and act as the fallback for a fresh deployment.
Editing `.env` after the first run has no effect.

Filter criteria are set in two places. The global title patterns are on
`/settings`. Each profile's own title patterns and experience level are on
`/profiles`. A change applies to the next run automatically. To apply it to
postings already collected, run `filter --all --dry-run` to see what would
change, then `filter --all` to apply it. The
[operations guide](Docs/operations-guide.md) explains how the two levels combine
and why the search term should name the role without a seniority word.

> **The shipped defaults are one person's job search.** `SEARCHES` looks for
> data engineering roles in Cairo and `TIMEZONE` is `Africa/Cairo`. These are
> seed values, meant to be replaced on first run from the Schedules and Settings
> pages — they are examples of the shape a search takes, not a statement of what
> the project is for. Change them to your own before the first collection run.

---

## Documentation

The full documentation set lives in **[Docs/](Docs/)** — start with
[Docs/README.md](Docs/README.md), which indexes it and gives a reading order.

| Document | Read it for |
|---|---|
| [Design record](Docs/job-discovery-pipeline-design.md) | Why the system is shaped this way |
| [SRS](Docs/software-requirements-specification.md) | What it is required to do |
| [System architecture](Docs/design/system-architecture.md) | Structure, stages, runtime topology |
| [Data model](Docs/design/data-model.md) | Entities, relationships, schema |
| [Deployment guide](Docs/deployment-guide.md) | Standing it up |
| [Development guide](Docs/development-guide.md) | Working on the code, in depth |
| [Operations guide](Docs/operations-guide.md) | Running it day to day |
| [ADRs](Docs/README.md#architecture-decision-records) | Why one specific choice was made |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). It carries the conventions that are not
guessable from the code — the dependency direction above, the `OBSERVED` test
fixture rule, the non-merging assertion requirement, the migration review
workflow, and when a change needs an ADR.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Legal and usage

This pipeline scrapes job boards and stores personal data locally. Read
[NOTICE.md](NOTICE.md) before running it — it covers board terms of service,
rate limiting, and your responsibilities as the operator.

## Licence

[Apache License 2.0](LICENSE). Third-party dependency notices are in
[NOTICE.md](NOTICE.md).
