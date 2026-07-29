# ADR-0011: `job_type` taxonomy for the work-arrangement-mix report

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Corrects [Reports implementation plan](../design/reports-implementation-plan.md) §5 R6, which assumed `job_type` needed normalisation without checking the source |
| **Related** | [ADR-0008](0008-report-system-scope.md) R6; [db/models.py](../../app/src/app/db/models.py) `Posting.job_type`; `python-jobspy` dependency (`pyproject.toml`) |

---

## Context

The reports plan flagged `job_type` as "stored verbatim from the collector
payload and not normalised anywhere," predicted variants such as `fulltime`
versus `Full-time`, and made "enumerate distinct values against real data"
a prerequisite for R6 — a prerequisite this session cannot satisfy, since no
database is currently running.

That prediction turns out to be wrong, and checkable without a database. The
design record's own governing rule — "where measurement and estimate
disagree, the measurement governs" (§4.3) — applies here even though the
thing being measured is a dependency's source rather than a live board:
`python-jobspy` is an installed package, not an opaque network service, and
its normalisation logic is inspectable directly.

`.venv/Lib/site-packages/jobspy/model.py:10-57` defines `JobType` as a Python
enum with ten members (`FULL_TIME`, `PART_TIME`, `CONTRACT`, `TEMPORARY`,
`INTERNSHIP`, `PER_DIEM`, `NIGHTS`, `OTHER`, `SUMMER`, `VOLUNTEER`), each
holding a tuple of recognised strings across languages —
`FULL_TIME`'s tuple alone lists board-reported variants in over twenty
locales. `jobspy/__init__.py:130-140` shows exactly where that gets collapsed,
inside the per-job, per-board loop that builds each row *before* any
DataFrame assembly:

```python
job_data["job_type"] = (
    ", ".join(job_type.value[0] for job_type in job_data["job_type"])
    if job_data["job_type"]
    else None
)
```

`job_type.value[0]` is each enum member's canonical first string —
`"fulltime"`, `"parttime"`, `"contract"`, `"temporary"`, `"internship"`,
`"perdiem"`, `"nights"`, `"other"`, `"summer"`, `"volunteer"`. So what reaches
`normalise_stage.py` and lands in `Posting.job_type` is never a raw
board string: it is already lowercase, already collapsed out of twenty-plus
locale variants, drawn from a closed ten-member vocabulary. The one real
source of variation is that a posting can carry more than one type — the list
comprehension runs over `job_data["job_type"]` as a list — so a role tagged
both full-time and contract serialises as the literal string
`"fulltime, contract"`. `None` is the value when a board declared no type at
all.

The plan's predicted failure mode — case or spelling drift needing a
normaliser under `src/app/normalise/` — does not exist. The real design
question is different: how to present the closed vocabulary, and how to
handle the two things that *are* real: multi-type combination strings, and a
third-party enum silently changing under this project's feet on a future
upgrade.

## Options considered

**A — Trust the enum as the taxonomy; ship the crosstab now**, treating each
distinct `job_type` string (including combination strings like
`"fulltime, contract"`) as its own category, with no grouping logic at all.

*Simplest, and grounded in the evidence above rather than a guess.* No
normaliser, no `src/app/normalise/` addition, nothing conditional on data that
does not exist yet. A combination string is rare enough in practice (JobSpy
only populates the list when a board declares more than one type) that
treating it as its own row is honest rather than lossy.

**B — Split multi-type strings into per-value membership**, so a posting
tagged `"fulltime, contract"` is counted once toward `fulltime`'s total and
once toward `contract`'s, mirroring how R3 already treats multi-board overlap:
a combination is its own reported category *and* each member contributes to
its own per-value total (`services/reports.py::source_overlap` —
`per_site` versus `combinations`).

*Consistent with existing house style* for exactly this shape of problem —
R3 already made the "both a combined category and a per-member count" call
and R6's data has the same structure (a small set of tags, sometimes more than
one per row). *Cost:* the report needs two tables instead of one wherever this
applies, for a case JobSpy's design suggests is uncommon.

**C — A drift guard: pin the assumption with a test.** Add a test asserting
the installed `python-jobspy` version's `JobType` enum still yields exactly
the ten expected `value[0]` tokens, so a future `python-jobspy` upgrade that
renames, adds, or removes a category fails the suite instead of silently
changing what R6's category list means.

*Addresses a real risk specific to depending on a third party's enum as this
project's own reporting taxonomy* — the project does not control
`python-jobspy`'s release notes, and a category rename upstream would
otherwise surface only as an unexplained new row in the crosstab. Cheap: one
test, no runtime cost.

**D — Wait for real data**, treating "enumerate distinct values in
production" as still mandatory before shipping R6, deferring the whole report.

*Rejected.* This is the plan's original position, and the reason to hold it
was the belief that the field needed cleaning before it could be trusted. That
belief is now checked and false — waiting adds delay in exchange for
confirming something already confirmed by reading the source. Worth doing
eventually as a sanity check once data exists (folded into Control below), but
not worth blocking on.

## Decision

**A, plus C.** Ship the crosstab against the raw `job_type` string with no
grouping logic, and add the drift-guard test so the taxonomy is pinned rather
than silently assumed.

B is not adopted now. It solves a real presentation question, but the
combination case JobSpy's own code shows is the exception, not the norm — most
postings carry exactly one type, since board listings are usually singly
classified — and building a second table for a rare case ahead of seeing how
often it actually occurs would be exactly the kind of speculative elaboration
this project has twice already ruled against (refactor-plan §1, §9). If
production data shows combination strings are common enough to be worth
splitting, B is a contained addition to an existing function, not a rewrite.

## Consequences

*Favourable:*

- Removes a false prerequisite that was blocking R6 on infrastructure
  (a live database) the actual question never needed.
- No `src/app/normalise/` addition for a normalisation problem that does not
  exist — avoids inventing code to solve a predicted defect that turned out
  not to be real.
- The drift guard converts a silent future risk (an upstream rename quietly
  relabelling a report category) into a loud, cheap, local test failure.

*Unfavourable, and accepted:*

- `None` (no type declared) and combination strings both need their own
  explicit, legible rows in the crosstab rather than being folded away —
  acceptable since both are genuine, board-reported states, not defects to be
  hidden.
- If combination strings turn out to be more common than JobSpy's design
  implies, the report under-serves anyone trying to read per-type totals
  until B is built. Accepted per the same "small, then measured" reasoning
  ADR-0008 applies to the whole report set — build the simple version, and let
  real usage justify the more elaborate one.

## Control

Once production data exists, confirm the assumption directly — a one-line
`SELECT DISTINCT job_type, COUNT(*)` — both to validate this ADR's reading of
the source and to measure how often combination strings actually occur, which
is what would justify B. This is verification of a decision already made, not
a prerequisite for it, which is the distinction that separates this Control
section from Option D above.
