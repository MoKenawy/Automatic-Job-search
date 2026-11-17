# Research: Collect-stage relevance and experience filtering

**Feature**: [003-collect-stage-filtering](spec.md) | **Date**: 16 November 2026

The feature's *what* is settled by the specification, whose three
`[NEEDS CLARIFICATION]` markers were resolved before planning and are recorded in
[checklists/requirements.md](checklists/requirements.md) iteration 2: experience
stays free text read through a synonym set, the experience criterion admits an
at-or-below band, and only the board-supplied seniority label is promoted out of the
payload. No markers were carried into this document.

What remained open was *how*, and the ten decisions below are the ones where a
plausible alternative existed. Each records what was rejected, because three of them
(R1, R3, R6) are places where the obvious implementation is actively wrong rather
than merely inferior.

---

## R1 — Where the experience criterion comes from

**Decision**: a posting is admitted on experience grounds if **any** search profile
that has ever surfaced it admits it; a contribution from a profile-less run admits
unconditionally. The verdict is a disjunction over the set of contributing profiles,
computed from stored state.

**Rationale**: the obvious implementation — read `run.profile_id` for the run being
filtered — is order-dependent, and the repository already documents why. A posting
can be surfaced by more than one profile's runs, as `services/reports.py:302-316`
states when explaining its own fan-out: *"a posting can be surfaced by more than one
profile's runs (or by none, via a profile-less manual run-all). Rather than pick one
profile to credit, every matching profile counts the posting."*

So a posting reachable from profile A (`fresh`) and profile B (`senior`) would carry
whichever verdict the most recent run happened to compute. Three spec requirements
break at once: FR-010 (idempotence — the verdict alternates with run order rather
than converging), SC-007 (re-apply is identical only *per run id*, which is weaker
than what the spec states), and `filter --all` has no defined meaning at all because
there is no single `run.profile_id` to read.

Disjunction is commutative, associative and idempotent, so the verdict becomes a
total function of `(posting.job_level, posting.normalised_title, {profile.experience})`
and nothing else. That is what reduces SC-007 to "the function is pure and nothing
is timestamped". It also runs with FR-005 and FR-009 rather than against them:
preferring the admitting signal is exactly "prefer an informative signal from any
contributing row over the absence of a signal in another".

**Consequence accepted**: a posting touched by a profile-less `run-all` is
permanently admitted on experience grounds, because no requested level exists to
compare it against (the spec's own assumption). On the live database no profile-less
run exists, so nothing is affected today; after one manual `run-all`, every posting
it touches becomes permanently exempt from the experience criterion. That caps what
SC-001 can demonstrate on a mixed corpus, and is the price of the spec's assumption
rather than of this decision.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Read `run.profile_id` for the run being filtered | Order-dependent; breaks FR-010 and SC-007 in normal operation, and leaves `--all` undefined. This is the design's one genuinely wrong answer |
| A per-profile verdict table (`posting_id`, `profile_id`, verdict) | The only *fully* correct model of a per-profile criterion, and still rejected: the triage list has no profile context at read time, so a per-profile verdict could not be enforced by a read-time predicate at all. It would be recorded and unenforceable |
| Ignore profile-less contributions when a profile-attributed one exists | Defensible, and it would preserve more of SC-001's demonstrable effect. Rejected as a silent narrowing of the spec's stated assumption; if the exemption becomes a nuisance in practice, this is the change to make, and ADR-0016 names it |
| Thread `experience` through `SearchSpec` | `SearchSpec` is one collector invocation and the collector has no experience parameter (verified against the vendored JobSpy). Adding a field there would put a filter criterion in the collector's vocabulary for no gain |

---

## R2 — Which direction the merged signal leans, and what the fallback may do

**Decision**: where several collected rows fold into one posting, the stored
`job_level` is the **minimum** seniority across the contributing labels, with ties
between labels that parse to the same level broken lexicographically on the raw
label. The board's own label is stored verbatim. The title-derived fallback is
computed at evaluation time and **never** persisted.

**Rationale**: "backfill when NULL" converges but is not *defined* — the stored
label would be whichever contributing row happened to have the lowest id, forever.
FR-009 asks for more than convergence: the verdict "must be defined for the merged
posting, not left to whichever row happened to be processed last". Minimum is
commutative, associative and idempotent, so the merged value is a function of the
*set* of contributing rows.

Minimum is also the direction the governing asymmetry demands. Rejection happens
only *above* the requested level (FR-007), so the lowest contributing label is the
admitting one, and a disagreement between boards resolves toward showing the
operator the posting.

The tie-break matters for SC-007 and is not pedantry: two labels parsing to the same
level (`mid-senior level` from one board, a hypothetical `Mid-Senior` from another)
would otherwise store whichever was seen first, and a re-apply could store the
other.

Keeping the fallback out of the column follows ADR-0012's lesson directly. That ADR
exists because one column carried two meanings until the two were split;
`postings.job_level` is named after a payload field, so writing an inference into it
would make "what did the board say?" unanswerable from the schema.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Fill the gap on first sight, never overwrite | Order-dependent; FR-009 asks for a defined merged value, not merely a stable one |
| Last writer wins | Order-dependent, and leans toward rejection when boards disagree — against the asymmetry |
| Store a derived level rather than the label | Loses FR-019's "typed and directly inspectable" board value; the parsed level is recoverable from the label at any time, but not the reverse |
| Persist the title-derived fallback into `job_level` | Conflates an inference with a board statement in a column named after the board's field. ADR-0012 is the precedent for refusing this |

---

## R3 — What an empty pattern means, and what the title is matched against

**Decision**: an empty or whitespace-only pattern means *the criterion is disabled*,
decided **before** anything is compiled. The criteria are matched
case-insensitively against `Posting.title` — the title as the boards gave it and as
the operator sees it.

**Rationale**: `re.search("", title)` matches every string. Both patterns ship empty
(`config.py:64-65`), so compiling the default naively and asking "does the exclude
pattern match?" rejects the entire corpus on the first run after installation. It is
the highest-consequence bug available in this feature, it would pass any test that
only checks that rejection works, and it directly violates SC-006. Treating empty as
*disabled* before compiling removes the possibility rather than guarding against it,
and it gets a test named for SC-006.

Matching against `title` rather than `normalised_title` is the operator-facing
choice: they write the pattern after reading titles in the triage list, and
`normalise_title()` folds accents, strips punctuation and removes requisition ids,
so a pattern containing `C++` or a hyphen would behave surprisingly against the
normalised form. Case-insensitivity is supplied by `re.IGNORECASE` so the operator
need not think about it.

The title-derived seniority fallback (R2) is the one place `normalised_title` *is*
the right input: it is already lowercased and punctuation-free, which is what
word-boundary marker matching wants, `normalise/title.py` deliberately retains
seniority words, and the value is already stored on the posting.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Compile the empty pattern and special-case the match result | Puts the corpus one forgotten branch away from vanishing. The absence of a pattern is a fact about the criteria, not about a match |
| Match the normalised title | Surprising for hand-written patterns: punctuation and requisition ids are gone, so the operator's pattern and the string it runs against differ visibly |
| Match title and description | SRS FR-16 confines the filter to the title, and D6 says a regex is "unsuitable for requirement analysis, where unstructured phrasing produces false negatives" |

---

## R4 — Hiding is not the same fact as rejection

**Decision**: two expressions in `db/visibility.py`. `filter_rejected()` is the pure
verdict — a posting a criterion rejected, whatever its triage status.
`hidden_by_filter()` is `filter_rejected() AND status == 'new'`, and it is
`~hidden_by_filter()` that the read paths adopt. The "Filtered out" review bucket
uses `filter_rejected()`, **not** the complement of the hide rule.

**Rationale**: the spec's edge case is explicit — "a posting the operator has
shortlisted or applied to must not be removed from view by a later tightening of the
filter". Triage is the operator's own judgement, and a criteria change must not
reach back and withdraw something they have acted on. So the hide rule needs a
status term, while the verdict must not have one, or FR-016's "which criterion
rejected it" becomes unanswerable for a posting that was triaged.

The bucket then deliberately overlaps the normal list: a posting that is *rejected
and not new* appears in both. That is the point. FR-017 and SC-002 exist to make
**false** rejections discoverable, and the strongest available evidence of a false
rejection is a posting the operator shortlisted which the current criteria reject.
Defining the bucket as "everything hidden" would hide exactly that evidence.

Because the two sets are different, they can drift apart silently, so a partition
test over every (verdict × status) pair asserts `hidden + visible == all` and names
the overlap set rather than leaving it to be rediscovered.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| One predicate, hiding every rejected posting | Withdraws postings the operator has shortlisted or applied to — the spec forbids it |
| One predicate with no status term, plus a status filter at each call site | Same rule restated per read path, which is how a read path forgets it. ADR-0015's whole argument is that there must be one thing to apply |
| Bucket defined as the complement of the hide rule | Conceals the most valuable false-rejection evidence, and makes the bucket's meaning depend on the hide rule's status term |
| Hide only `new` **and** unscored | Scoring does not exist yet; adding a term for it now would be speculative |

---

## R5 — Making SC-007's "byte-identical" literally true

**Decision**: every verdict write is guarded by a difference check, so a converged
re-apply issues **zero** UPDATE statements. The counters are recomputed from the
evaluated set rather than accumulated.

**Rationale**: `Posting.updated_at` carries `onupdate=func.now()`. Re-assigning
`title_filter_passed = True` to a row that already holds `True` still emits an
UPDATE, which moves `updated_at` — so a second `filter --all` over unchanged data
would change a thousand rows' timestamps. SC-007 says "byte-identical verdicts and
identical counts", and under a blind write that is false in the letter even though
every verdict agrees.

Guarding the write also makes the property cheap to check: run `filter --all`
twice and the second run reports zero changes. That is the quickstart's Gate 2.

The same reasoning rules out a `filtered_at` timestamp column. It would be the only
field in the design capable of making SC-007 unfalsifiable, which is reason enough
not to have it — and "when was this verdict computed?" is answerable from the run
counts and the log without storing it per row.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Write unconditionally; accept timestamp churn | Breaks SC-007 as written, and makes `updated_at` — already carefully separated from `last_retrieved_at` by ADR-0012 — move for a reason that is not a change |
| Suppress `onupdate` for this write path | Dialect- and ORM-level trickery to preserve a property that a two-line comparison preserves honestly |
| Add `filtered_at` for auditability | The only field that could make SC-007 unfalsifiable. The run counters already carry the "when" |

---

## R6 — The predicate must be NULL-safe, and provably so

**Decision**: the verdict predicate is written with `.is_(False)` on both columns —
never `== False`, never `~(column == True)` — and the hazard is stated in
`db/visibility.py`'s docstring at the definition site.

**Rationale**: every verdict column is NULL for all 52 existing postings, and NULL
is the normal steady state under SC-006. Under SQL's three-valued logic
`NOT (NULL = FALSE)` is NULL, and a row whose WHERE clause evaluates to NULL is
**not** selected. A predicate written the obvious way therefore hides the entire
corpus the moment it is adopted — and every absence-only test passes, because
everything is absent.

002's contract already names this exact failure for the other seam:
*"An absence-only suite passes against a `not_suppressed()` that returns `false` and
hides the entire corpus — the seam would be catastrophically wrong and every test
green"* ([visibility-seam.md](../002-employer-suppression-derived/contracts/visibility-seam.md)).
The containment is the same: every test two-sided, over a corpus that holds NULL,
True and False verdicts crossed with all four statuses.

`IS FALSE` is rendered identically by SQLAlchemy under SQLite and PostgreSQL and
involves no JSON operator, so this feature needs no dialect split — unlike
`queries._has_source`, which needed one because SQLite's `JSON_QUOTE(NULL)` yields
the *string* `'null'` and silently defeated an `IS NOT NULL` test. That contrast is
worth keeping in view: it is the strongest concrete argument for FR-019's promotion
of `job_level` to a column, since reading the label out of JSONB in a query would
land in precisely that trap.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| `column == False` | Three-valued logic; hides every NULL-verdict posting, which is all of them today |
| `coalesce(column, True)` | Correct but obscures what is being asked, and invites a reviewer to simplify it back into the bug |
| A NOT NULL column with a default | Destroys the distinction between "criterion not applied" and "applied and admitted", which is what makes SC-006 checkable (see [data-model.md](data-model.md)) |

---

## R7 — Two Alembic revisions, and where the backfill rule lives

**Decision**: a DDL revision adding both nullable columns, then a separate data
revision backfilling `job_level`, which **imports** `app.filters.levels` rather than
restating the merge rule.

**Rationale**: the house pattern is exactly this split —
`a1b2c3d4e5f6_raw_posting_normalizations_link.py` adds the table, and
`b2c3d4e5f6a7_backfill_raw_posting_normalizations.py` fills it, importing
`build_fingerprint` from the application rather than reimplementing the digest. The
reason is the one that applies here: if the migration restates the rule, then
installation and the first `filter --all` can disagree, and SC-007 fails on day one
through a divergence no test would look for. One test asserts the backfilled value
equals a fresh evaluation.

Both columns are nullable, with no server default. `job_level` has 0% coverage on
one of the two working boards, so any default would be a claim about data that does
not exist; and the verdict columns' NULL is load-bearing (R6, data-model). This
follows `e2494af987ca`'s "nullable and additive" shape rather than
`dc0d779245f2`'s "NOT NULL with a server default dropped immediately", because there
is nothing to backfill the verdicts *from*.

No index is added. Per 002's G5, correctness must not depend on one, and at NFR-1
volume — under a hundred postings — the plan difference is not measurable.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| One revision doing DDL and data together | Against the established split, and it makes the DDL unreviewable separately from a rule that may change |
| Pure SQL backfill (`payload->>'job_level'`) | Expressible, but it would restate the min-wins and tie-break rule in a second language. The precedent is to import the rule |
| Backfill the verdict columns too | Would make installation itself a filtering event, which the spec's assumption forbids: "existing postings are not retroactively filtered on installation" — that is an operator action |
| Index the verdict columns | Correctness must not depend on an index, and at this volume it buys nothing measurable |

---

## R8 — The filter's primary input has a hidden switch

**Decision**: record the coupling rather than defend against it. ADR-0016 states it,
and the `/settings` form notes it beside the field.

**Rationale**: the collector only populates `job_level` when LinkedIn job
descriptions are fetched, and `linkedin_fetch_description` is an operator-editable
setting that is already consumed. Turning it off takes the experience criterion's
primary input from 100% coverage to 0% on the only board that supplies it — and
because unknown admits (FR-005), the criterion then silently stops rejecting
anything.

That failure direction is the right one: the filter fails *open*, so no posting is
wrongly withheld. What is wrong is the silence. An operator who switches
descriptions off to speed up collection has no way to know they also switched off
seniority filtering. A note at the field is the cheapest honest fix; making the
filter re-enable the setting, or refuse to run without it, would be the system
overriding an operator's deliberate choice.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Force `linkedin_fetch_description` on when an experience criterion exists | Overrides a deliberate operator setting from an unrelated screen |
| Warn per run when coverage collapses | Worth having later, and it needs a coverage baseline to compare against. The stage already logs the unknown count, which is the raw material |
| Say nothing — it fails open | Fails open *silently*, which is the half this decision is about |

---

## R9 — The specification's baseline no longer describes this database

**Decision**: keep the spec's narrative and requirements as written, and record the
re-measurement taken for this plan. FR-020's correction is narrowed to the two
claims that are actually false.

**Rationale**: the spec cites 32 runs, 1,092 collected rows and a "Backend
Developer" profile recording `fresh`. Measured on 16 November 2026 the database
holds 60 raw rows across 2 runs, 52 postings and 3 profiles — `data engineer`,
`data engineer (remote)` (both with no experience recorded) and `AI Engineer`
(`entry level`). The database has been rebuilt since the spec was written, so the
spec's baseline figures, and SC-001's "24% for the Backend Developer profile",
cannot be reproduced. Nothing in the design depends on them; they are evidence for
*why* the feature is worth building, and that argument stands.

What does reproduce is the shape the design depends on, and it is sharper than the
spec's figure: `job_level` is present on 100% of LinkedIn rows and 0% of Indeed
rows, so the 78% the spec quotes and the 67% measured today are both just the
board mix. One board always supplies the label; the other never does. That is
exactly the condition FR-006's title fallback and FR-005's "unknown admits" exist
to handle.

FR-020 asks for the recorded coverage measurement to be corrected "for all three"
of seniority, function and industry. Measured today: `job_level` 67% overall and
`company_industry` 67% — both documented in `db/models.py` as "never populated",
and both therefore false — while `job_function` is genuinely 0%, as are
`listing_type`, `skills` and `experience_range`. So the correction states the two
falsified claims with their real figures and confirms the third rather than
rewriting it, and function and industry stay in the payload as the spec directs.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Amend the spec's figures to today's | The spec is a record of what was observed when it was written; rewriting its evidence would destroy the audit trail ADR-0015 exists to protect. The plan records the re-measurement instead |
| Treat the discrepancy as a blocker | The requirements do not depend on the magnitude, only on the pattern, and the pattern holds |
| Correct all four documented fields identically | Two of the four claims are true. Rewriting them would trade one inaccurate record for another |

---

## R10 — Its own stage, and what that does to ADR-0007's open question

**Decision**: a standalone, re-runnable stage between stage 2 and the planned
scoring stage, framed as *extracting D6's filter out of stage 3* rather than as a
new "stage 2.5". Stage numbering in the design record is left intact.

**Rationale**: `db/models.py` and `system-architecture.md` §5.3 both place the
coarse title filter inside stage 3, which does not exist. Folding this feature in
there would mean the filter ships only when scoring does, and
`runs.filter_passed_count` stays unwritten for however long that takes. FR-010 and
FR-011 require a standalone entry point regardless — re-evaluating under changed
criteria without re-collecting is the whole of US3 — and once that exists, "inside
stage 3" would be merely a call site.

Separation also serves D6's own stated purpose better. With the verdict stored, the
scoring stage's candidate query becomes `not_suppressed() AND filter-passed`, which
is a seam adoption of the kind `system-architecture.md:163-167` already obliges,
rather than filtering logic inlined into the scorer.

This has a bearing on an open question elsewhere, and it is worth being explicit
about it. [ADR-0007](../../Docs/ADRs/0007-scoring-evaluation-and-score-history.md)
§O3 leaves the title pre-filter unresolved — "replace, demote, or drop" — and leans
toward replacing the regex with an embedding gate, with the regex demoted to an
availability fallback. This feature implements the regex gate D6 specifies, and so
does not settle O3. It does, however, produce the first of the three measurements
O3 says would settle it: ADR-0007 names "the filter's current drop rate, from the
`title_filter_passed` column already in the schema", and that column is unwritten
precisely because this filter was never built. Building it makes O3 answerable
instead of hypothetical, and ADR-0016 records that relationship so a later reader
does not take the two records to be in conflict.

**Alternatives considered**:

| Option | Rejected because |
|---|---|
| Fold into stage 3 when it is built | The counters stay unwritten indefinitely, and the feature cannot ship on its own |
| Evaluate inside `run_normalise` at promotion time | FR-011 needs re-evaluation without re-collection, which needs a standalone entry point anyway; and a stage that both creates and judges postings cannot be tested for "judgement never changes creation" (FR-012) |
| Renumber the pipeline and call it stage 3, pushing scoring to 4 | Churns every document, every comment and every count name for a presentational gain |
| Resolve ADR-0007 O3 first | O3 needs measurements that only a working filter can produce. Building the specified filter is the cheapest way to make the question answerable |
