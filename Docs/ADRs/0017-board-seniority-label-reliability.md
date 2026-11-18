# ADR-0017: Board seniority label — how far to trust it when it hides a posting

* Status: accepted — as built (18 November 2026)
* Deciders: Mohammed
* Date: 17 November 2026; decided 18 November 2026

Technical Story: after the collect-stage filter shipped (ADR-0016), most LinkedIn
postings stopped reaching the triage queue and the operator read it as "LinkedIn
is blocked". It is not: collection is healthy, and the postings are being hidden
by the experience criterion, on the strength of a field LinkedIn fills in
unreliably. The record was opened as proposed, to state the evidence and the
options before choosing. It is now accepted: the rule stays **as built**, with a
named measurement that would reopen it — see [Decision](#decision).

## Context and Problem Statement

**Collection is not the problem.** Across every run on file, LinkedIn returns
17–20 rows per search, every one carrying a description and a `job_level`.
Indeed returns 3–6 rows per search and a seniority level on none. Nothing is
blocked or missing; `runs.error` is empty on every run.

**What hides them.** A search profile may record an experience level in free
text ("entry level", "junior"). The filter reads that against the seniority the
board declared for the posting, and — per FR-007 of
[spec 003](../../specs/003-collect-stage-filtering/spec.md) — an entry-level
request admits everything up to `associate` and rejects `mid-senior level` and
above. LinkedIn's field has seven values, and `mid-senior level` is by far the
commonest:

| LinkedIn "Seniority level" | rows |
|---|---|
| mid-senior level | 83 |
| not applicable | 22 |
| entry level | 12 |
| associate | 4 |
| executive, director, internship | 1 each |

(124 LinkedIn rows, counted on 17 November 2026 before a fifth profile was
added.)

**Measured on the corpus as of 17 November 2026 — 135 postings, five profiles,
two of them stating no experience.** Under the rule as built, 82 postings are
hidden on the experience criterion. What drove each decision:

| Rejected because | postings |
|---|---|
| the board declared a level above the request **and the title says so too** | 40 |
| the board declared a level above the request **and the title is silent** | 25 |
| the board declared nothing, and the **title** carried an explicit seniority word | 17 |

The 25 in the middle row are the question. They are plain titles —
"Software Developer", "Backend Engineer", "Data Engineer-Data Integration",
"Product Manager", "Big Data Developer" — that LinkedIn marked `mid-senior level`.
Some of them genuinely are above an entry request ("Software Engineer 2",
"Technical Architect"). This record does **not** claim they are wrong; it claims
the operator has not been shown them, cannot recover them by looking harder, and
that nothing independent corroborates the board's word on them.

**The board's label is noisy in both directions**, which is what makes this more
than a threshold to tune:

| LinkedIn title | Its "Seniority level" | |
|---|---|---|
| Data Engineer (Coca-Cola HBC) | mid-senior level | over-labelled; hidden |
| Senior Denodo Data Virtualization Engineer | not applicable | under-labelled; shown |
| Business Intelligence Developer II | entry level | shown |
| Delivery/Driving Assoc Leader | mid-senior level | not a technology role |

**A caution about the title evidence.** The 17 title-read rejections look
reliable, but that is close to true by construction: `level_from_title` fires
only on an explicit seniority word ("senior", "lead", "principal"…) and returns
nothing otherwise, so it cannot be wrong in the way the board label can. It is a
conservative signal, not a validated one, and should not be cited as proof that
titles are better than labels in general.

**This is the specification working as written**, not an implementation defect.
FR-007 asks for exactly this behaviour. The assumption underneath it — that a
board-declared level is trustworthy enough to conceal a posting — was reasonable
before the data existed and is open to question now.

## Decision Drivers

* A posting wrongly hidden is one the operator never sees and cannot recover by
  looking harder; a posting wrongly shown costs seconds. This is the governing
  asymmetry of spec 003 and of deduplication before it.
* The operator has stated the filter should reduce triage work. A criterion that
  hides nothing does not.
* One board supplies the label on every row and the other on none, so any rule
  that leans on the label treats the two boards very differently.
* The label depends on `linkedin_fetch_description` being on
  ([ADR-0016](0016-collect-stage-filter-verdicts.md), Consequences); a rule that
  leans harder on it inherits that fragility.

## Options considered

Each measured against the same 135-posting corpus. "Hidden" is postings the
experience criterion would withhold from the queue.

| Option | Hidden | What it does | What it costs |
|---|---|---|---|
| **As built** | 82 | Board label decides; title only where the board is silent | The 25 uncorroborated rejections above |
| **A. Title must corroborate a board label before it may hide** | 57 | The label can still admit on its own; to hide, the title must also carry a seniority marker | Keeps the label as a signal but demotes it to an admitting-only one |
| **B. Judge from the title alone** | 57 | Ignore the label when deciding; treat both boards identically | Discards a signal LinkedIn supplies on every row |
| **C. Widen the entry band to reach mid-senior** | 2 | `associate` already sits in an entry request's band; add `mid-senior` | Also admits genuinely senior roles; the criterion becomes nearly inert on LinkedIn |
| **D. Advisory — display the level, never hide on it** | 0 | Show seniority as a sortable column | All 135 stay in the queue; the criterion stops saving triage work |

**A and B hide the same 57 postings on this corpus.** They differ in principle,
not in outcome, and the corpus is too small to separate them: A keeps the label
as an admitting signal and would behave differently on a posting whose label is
below the request while its title says "Senior"; B would not look at the label at
all. A choice between them should rest on that case, not on the headline count.

## Decision

**As built.** The board's label decides, and the title is read only where the
board declared nothing — the first row of the options table, 82 of 135 postings
hidden on this corpus. No behaviour changes; the filter keeps behaving as
ADR-0016 describes.

The 25 postings hidden on the board's word alone are accepted as the cost, for
now, because:

* they are **withheld, not lost** — each stays at `/postings?verdict=rejected`
  with its grounds, and a later change of rule restores it with its triage
  status intact (FR-011, FR-013);
* A and B hide the same 57 on this corpus, so the corpus cannot yet tell them
  apart, and changing the rule on a headline count would be choosing blind;
* the criterion exists to save triage work, and the as-built rule is the only
  option that does so on LinkedIn at full strength.

What this record does **not** settle is whether those 25 are mostly right. That
is a question of fact about the postings, and it gets an instrument rather than
a guess — next section. The two non-decisions stated when this was proposed
still hold: the label is not judged untrustworthy in general, and no
alternative option is preferred.

### Follow-up: a DeepEval indicator on the as-built rejections

*Recorded, not built.* An opt-in evaluation suite, using
[DeepEval](https://github.com/confident-ai/deepeval), whose result is the
signal for reopening this record.

* **What it judges.** Exactly the contested set: postings the experience
  criterion hides where the board's level is above the request **and the title
  is silent** (the middle row of the "Rejected because" table). It is built
  from the application's own functions, as [Control](#control) describes, so it
  measures the rule as shipped.
* **How.** A DeepEval `GEval` (LLM-as-judge) metric. Each test case is the
  requested experience, the posting's title and its description. The judge
  answers one question: on the description's own evidence (years required,
  scope, reporting line), is this role genuinely above the requested level? It
  is not shown the board's label, so it cannot simply repeat it.
* **Calibration first.** A small hand-labelled golden set (around 20 postings,
  labelled by the operator) fixes the judge's criteria and threshold before any
  verdict counts. A judge that disagrees with the operator on the golden set
  measures nothing.
* **The indicator.** The judged *false-rejection rate*: the share of the
  contested set the judge says is **not** above the request.
* **What would reopen this record**, either of:
  * the false-rejection rate exceeds **25%**; or
  * the contested set grows as a share of everything the experience criterion
    hides (25 of 82 today, about 30%).

  On either, evaluate **option A** (the title must corroborate the label before
  it may hide) on the then-current corpus, running the same suite over A's
  rejections for comparison.
* **How it runs.** Behind its own marker (for example `--eval`), never in the
  default suite. It needs an LLM API key and costs money on every run, and a
  judge's output is evidence, not a test that should fail a build.

The 25% threshold is a proposal; it is the operator's to move.

## Consequences

* On LinkedIn-heavy corpora with an entry- or junior-level profile, a majority
  of postings will be withheld from the queue. They remain reachable at
  `/postings?verdict=rejected`, each with its grounds, and re-applying the filter
  after any change restores them with their triage status intact.
* A profile whose experience box is blank behaves differently from one with a
  value: it votes to admit for every posting it surfaced. That is current,
  documented behaviour (see the operations guide) and is a separate question from
  this one.
* If description fetching is turned off, the label disappears and so does the
  problem — and the experience criterion with it, silently.

## Relationship to other records

Extends [ADR-0016](0016-collect-stage-filter-verdicts.md), which decided *how*
verdicts are computed, stored and enforced and which recorded the
`linkedin_fetch_description` coupling. This record questions an input to those
verdicts, not their mechanism, so nothing in ADR-0016 is superseded.
Relates to [ADR-0007](0007-job-scoring-model.md) §O3 for the same reason ADR-0016
did: the title filter and the experience criterion are the first measurements of
whether a coarse pre-filter hides things the scorer would have wanted.

## Control

Re-measure before revisiting, and run the DeepEval indicator above once it
exists. The split by decisive signal can be reproduced from
the application's own functions (`app.filters.levels.parse_level`,
`level_from_title`, `admits_any`, over
`app.db.attribution.requested_experience_by_posting`), and the corpus will have
grown. If the "board label, title silent" row has become a small fraction of the
hidden set, the decision has held up; if it has grown, that is the second
reopening trigger in the follow-up above.
