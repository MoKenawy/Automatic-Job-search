# Contributing

Thank you for considering a contribution. This document covers the conventions
that are **not** guessable from reading the code. Please read the sections on
the dependency direction, test fixtures, and non-merging before opening a pull
request touching the pipeline — they are the rules most often broken by
otherwise good changes, and they are what reviewers check first.

The [Development Guide](Docs/development-guide.md) is the fuller treatment of
everything here. This file is the contract; that one is the tutorial.

---

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Docker. Python 3.12 is pinned by
`app/.python-version` and installed by uv — do not install it yourself.

```bash
git clone https://github.com/MoKenawy/Automatic-Job-search.git
cd Automatic-Job-search/app

uv sync                              # exact locked graph, including dev tools
cp .env.example .env
docker compose up -d postgres        # only needed for migrations and running
uv run pytest                        # should pass with no database at all
```

**Every command runs from `app/`.** The Python project is nested; the
repository root holds documentation only.

### Before you push

```bash
cd app
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

CI runs exactly these, plus a migration round trip and a Docker build.

---

## The rules reviewers enforce

### 1. The dependency direction is load-bearing

```
config.py  ←  everything          (config depends on nothing)
collect/, normalise/              pure transforms, no database knowledge
pipeline/                         composes them; the ONLY layer that persists
web/                              reads the DB; never writes pipeline data
```

- `normalise/` and `collect/` must not import a session, a model, or anything
  from `db/`. They are pure functions over strings and dataclasses, which is
  precisely why the fingerprint logic can be tested exhaustively with no
  infrastructure. A single `from app.db import ...` in `normalise/` destroys
  that property for everyone.
- `web/` may write **triage status only**. It must never write postings,
  employers, or run records.

A change that needs to violate this is a design discussion, not a refactor to
fold into a feature PR. Open an issue or write an ADR.

### 2. Never read `os.environ` outside `config.py`

Add a field to the `Settings` class in [`app/src/app/config.py`](app/src/app/config.py)
instead. It is then validated by pydantic at startup, typed at every call site,
and visible in `uv run python -m app config`. A stray `os.environ.get(...)`
elsewhere is invisible, unvalidated, and untestable.

Complex values are accepted as JSON strings through a validator — see
`_parse_searches` for the pattern.

Note the resolution order for operational settings: **database → environment /
`.env` → code default** (ADR-0005). A new *operational* setting usually belongs
in `RunConfig` and `EDITABLE_KEYS` as well, so the UI can manage it.

### 3. Fixtures marked `OBSERVED` are real, captured strings

They are real values captured from live job boards, and they are the reason the
normalisation rules exist. **Do not "tidy" them.** `القاهرة, C, EG` is not a
typo, is not mojibake, and must fingerprint identically to `Cairo, Egypt`.

If a fixture looks wrong, it is evidence about a board's output, not a defect.
When normalisation logic changes, validate against real captured output — not
only against handcrafted fixtures that happen to encode your assumptions.

### 4. Assert non-merging at least as hard as merging

This is the governing design constraint, not a style preference:

> **A false merge conceals a posting. A false split merely repeats one.**

A test that proves cosmetic variants collapse (`Sr.` → `Senior`) is only half a
test. The other half proves that meaningfully different roles stay **distinct** —
seniority variants, discipline variants, different employers with similar names.
A PR touching `normalise/` that adds only merging assertions will be asked for
the separation cases.

```python
# Not sufficient on its own:
assert fingerprint("Sr. Data Engineer") == fingerprint("Senior Data Engineer")

# The half that actually protects the user:
assert fingerprint("Senior Data Engineer") != fingerprint("Data Engineer")
assert fingerprint("Data Engineer") != fingerprint("Data Analyst")
```

The pull request template has a checkbox for this. It is not a formality.

### 5. Comments cite the decision they implement

Comments explain **why**, and name the source of the reasoning — `ADR-0004`,
`design §7.3`, `D12`. This keeps the code traceable back to the record that
justifies it, which is what makes the design documents worth maintaining.

```python
# Design §9.3 — conservative by default; raising this is the first remedy
# for restriction, proxy provision the last
request_delay_seconds: float = 10.0
```

Do not narrate what the code plainly does. Match the density of the surrounding
code.

---

## Changing the schema

Models in [`app/src/app/db/models.py`](app/src/app/db/models.py) are the source
of truth. Alembic reads the database URL from `app.config.settings`, **not**
from `alembic.ini`.

```bash
cd app
uv run alembic revision --autogenerate -m "describe the change"
```

**Then review the generated migration by hand.** Autogenerate is a starting
point, not an authority:

- It does **not** detect data migrations or `CREATE EXTENSION`. The `vector`
  extension was added by hand for exactly this reason.
- **A new `NOT NULL` column on a populated table needs a `server_default`** for
  the backfill, dropped immediately afterward so the schema matches the model.
  Both early migrations demonstrate the pattern.
- **Carry data across before dropping the column it lived in.** The
  Notion→status migration moves `suppressed` into `status = 'rejected'` before
  dropping it.

Verify the round trip — CI runs this, and a broken downgrade is only discovered
when a rollback is needed under pressure:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1     # must succeed
uv run alembic upgrade head
uv run alembic check            # models and schema must agree
```

**One head, one chain.** If your branch adds a migration and another branch
also adds one, the second to merge must be rebased so its `down_revision`
points at the first. Merging two migrations that both claim the same parent —
or one whose parent lives only on an unmerged branch — leaves `main` unable to
run `alembic upgrade head` at all, which breaks `docker compose up` entirely
because the `migrate` service gates `web` and `scheduler`.

---

## Adding a pipeline stage

Follow the shape of `normalise_stage.py`:

1. Put the **pure logic** in its own package (e.g. `app/score/`), free of
   database concerns, with its own tests.
2. Add a **persistence function** in `app/pipeline/` that reads from the
   database, calls the pure logic, and writes results.
3. Wire it into `__main__.py` as a subcommand **and** into `run-all`.
4. **Update `runs` counts** so the stage is observable (design §7.4).
5. Validate against real stored postings before trusting the output.

**Stages must be idempotent.** Re-running against the same input must converge
on the same state. This is what makes it safe to re-run a failed pipeline.

---

## Architecture Decision Records

ADRs live in [`Docs/ADRs/`](Docs/ADRs/) and are **numbered and immutable once
accepted**. An ADR is never edited to reflect a changed mind — a later ADR
*supersedes* it, and the earlier record is retained so the reasoning history
stays legible. See [`Docs/README.md`](Docs/README.md) for the index and the
current supersession chain.

**Write an ADR when a change:**

- alters the schema in a way that constrains future work;
- changes a stage's contract, or the dependency direction above;
- picks between approaches whose trade-off a future reader would otherwise
  have to reconstruct;
- reverses or narrows an existing ADR.

**You do not need one for:** bug fixes, added test coverage, documentation,
refactors that preserve behaviour and structure.

If you are unsure, open an issue and ask before writing the code.

### Feature specifications

Larger features are specified in `specs/NNN-slug/` before implementation
(`spec.md`, `plan.md`, `tasks.md`, `research.md`). **The branch name matches the
directory name** — `002-employer-suppression-derived` is specified in
`specs/002-employer-suppression-derived/` and built on a branch of the same
name. Existing examples: `001-ui-self-service`, `002-employer-suppression-derived`.

Small changes do not need a spec. Use a `fix/`, `chore/` or `docs/` branch.

---

## Commits and pull requests

**Conventional Commits**, matching the existing history:

```
feat(web): filter and paginate the postings list by location and source
fix(pipeline): apply request_delay_seconds, reload scheduler, thread config
docs(adr): record ADR-0012 retrieval-date column split
refactor(suppression)!: derive suppression from employer, drop the sweep
test(reports): rename fixture employer "Ghost" to "Blacklisted"
```

Scopes in use: `web`, `db`, `pipeline`, `collect`, `normalise`, `reports`,
`adr`, `spec`, `design`, `ui`, `triage`, `app`. A `!` marks a breaking change.

Pull requests should be scoped to one concern, keep the test suite green, and
fill in the template — particularly the stage, the migration question, and the
non-merging checkbox.

---

## Running the secret scan locally

CI runs [TruffleHog](https://github.com/trufflesecurity/trufflehog) on every
pull request and over the full history on pushes to `main`. To run the same
scan before pushing:

```bash
# Install (macOS/Linux; see the project README for other platforms)
brew install trufflehog
```

From the **repository root**, not `app/`:

```bash
# What CI runs on a pull request — your branch's commits only
trufflehog git "file://." \
  --since-commit origin/main \
  --branch HEAD \
  --config .trufflehog/config.yaml \
  --include-paths .trufflehog/includes.txt \
  --exclude-paths .trufflehog/excludes.txt \
  --exclude-detectors lob \
  --results verified,unknown,unverified \
  --no-update --fail

# What CI runs on main — the whole history
trufflehog git "file://." \
  --branch main \
  --config .trufflehog/config.yaml \
  --include-paths .trufflehog/includes.txt \
  --exclude-paths .trufflehog/excludes.txt \
  --exclude-detectors lob \
  --results verified,unknown,unverified \
  --no-update --fail
```

`--branch` is not optional in the first command. Without it, `--since-commit`
walks every ref reachable since that commit, so you get findings from other
people's branches and cannot tell which are yours.

On Windows use `file://.` exactly as written — Git Bash expands `$PWD` to
`/d/Projects/...`, which TruffleHog reads as the nonexistent `D:/d/Projects/...`
and fails with a clone error rather than a scan result.

Two things that will otherwise waste your afternoon:

- **`--fail` exits with code 183**, not 1, when it finds something.
- **The path filter files hold one regex per line, not globs.** `*.py` there
  means "zero or more `p`s followed by `y`". Write `\.py$`.
- `--exclude-detectors lob` is not optional: Lob's test API keys have the same
  shape as a pytest function name (`test_` plus a long lowercase-underscore
  string), so without it the scan reports ~100 test names as *verified* secrets.

### When the scan flags something

1. **A real credential** — rotate it first. It is in the git history; deleting
   the line does not make it safe.
2. **A placeholder in documentation** — rewrite it so it does not parse as a
   credential. Angle-bracket the parts: `http://<user>:<pass>@<host>` passes,
   whereas the same string with the brackets removed is flagged, because that
   form is a syntactically valid credentialed URL.

   <!-- This paragraph deliberately does not spell out the bare form. When it
        did, the scan flagged CONTRIBUTING.md itself. -->

3. **A legitimate local default** — add it to the relevant
   `exclude_regexes_match` list in `.trufflehog/config.yaml`, **with a comment
   explaining why it is not a secret**.

Never silence a finding by adding the file to `.trufflehog/excludes.txt`. That
removes the whole file from every detector's view, not just the one that fired.

### What must never be committed

The root `.gitignore` covers these, but the rule matters more than the file:

- `app/data/` — the operator's CV and collected postings (personal data)
- `app/.env` — local credentials
- `Docs/AI-LOGS/` — raw model transcripts, unreviewed for disclosure
- TruffleHog output — a scan report contains the findings verbatim

---

## Reporting security issues

Do **not** open a public issue. See [SECURITY.md](SECURITY.md).

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
