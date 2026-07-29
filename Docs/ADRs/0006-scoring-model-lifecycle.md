# ADR-0006: Scoring model lifecycle — selection, training, testing

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 23 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Nothing directly; makes explicit what D5, D6, D8 and SRS §13 left unstated |
| **Related** | [Design record](../job-discovery-pipeline-design.md) D5–D8, [SRS](../software-requirements-specification.md) §3.4 (FR-16–20), §13 |

---

## Context

Stage 3 (scoring) is specified but unbuilt. The design record fixes some of its
shape — score locally via Ollama (D5), a 7–8B instruction-tuned model (D8), a
regex title pre-filter that is never used for requirement analysis (D6) — but
three questions a scoring system needs answered before it can be trusted were
never decided:

1. **Model selection.** D8 names a size class, not a method for choosing among
   candidates within it, or criteria beyond "adequate."
2. **Training.** No document states whether the model is used as-is, prompted,
   or fine-tuned. This is not a neutral omission: fine-tuning implies a labeled
   corpus, a training pipeline, and a GPU-time budget, none of which exist or
   are planned anywhere in the project.
3. **Testing.** D8 names one check — "JSON validity ... on twenty postings" —
   which verifies the model's output *parses*, not that it *agrees with the
   operator*. Design record §12 item 9 calls this distinction the most commonly
   omitted step and the most important one, then does not specify a method for
   it. SRS §13 lists the CV, model confirmation, and threshold calibration as
   blocking items, but names no process for any of the three.

This system is a single-operator pipeline scoring fewer than one hundred
postings a day (NFR-1) with a zero recurring-cost mandate (NFR-3, D5). Every
decision below is sized to that, not to a general-purpose scoring service.

## Decision

### 1. Model selection

Criteria, in order:

1. **Structured-output reliability** — passes the D8 JSON-validity check
   cleanly, not "usually."
2. **Context window** — must hold the full CV, the full job description, and
   the skill taxonomy in one call; no chunking.
3. **Throughput on the host GPU** — bounded by NFR-1 (a full run within a few
   minutes), which at under 100 postings a day is a generous ceiling, not a
   binding one.
4. **License** — irrelevant to cost (D5), relevant only if output or weights
   are ever redistributed.

Method: once the CV is provisioned (the standing blocker, SRS §13 item 1), run
the existing twenty-posting JSON-validity check from D8 against each shortlisted
candidate. The model selected is whichever passes cleanly; a longer bake-off is
not warranted at this scale.

### 2. Training — prompt engineering only; fine-tuning is out of scope

The scorer is used through prompting alone. Fine-tuning is explicitly and
permanently excluded from this design, not merely deferred:

- No labeled training corpus exists or is planned.
- No fine-tuning pipeline or GPU-time budget exists in the technology stack.
- D5's own rationale — zero marginal cost, full prompt control — is a
  prompt-engineering framing; fine-tuning a 7–8B model for fewer than a hundred
  postings a day would be disproportionate to the workload it serves, in the
  same way ports-and-adapters and data-oriented design were rejected elsewhere
  in this project for the same reason (`Docs/design/refactor-plan.md` §1, §9).

Revisiting this requires a new ADR, not a prompt-file change. Prompt iteration
itself is expected and ordinary (FR-20 requires re-runnability after a prompt
change) — this decision is about training method, not about the prompt being
fixed.

### 3. Testing — two tiers, one automated, one manual

**Structural (automated, buildable now).** Unit tests over the model-response
parser, independent of the CV or a running Ollama instance: valid JSON is
accepted; malformed JSON, missing fields, and an out-of-range score are
rejected rather than stored (FR-18). Modeled on the existing test style —
mock the model call, assert accept/reject behaviour, the same pattern already
used for JobSpy in `test_collect.py`.

**Judgement (manual, gates trust in the scorer).** The same twenty postings
used for the D8 JSON-validity check also receive the operator's own judgement,
recorded *before* running the model against them, to avoid anchoring on the
model's output:

- A binary call — would this posting have been shortlisted or rejected.
- Independently, the model's score, matched skills, gaps, and rationale for
  the same twenty.

**Acceptance criterion:** the scorer is trusted for real triage once its
shortlist/reject direction agrees with the operator's on at least 16 of 20
(80%) postings. Exact score agreement is not the bar — score is an ordering
device for the published list (design record, "Postings" entity), not a
value the operator is expected to agree with to the point. Disagreements are
read alongside the rationale (FR-25) to judge whether the prompt or the
threshold needs adjustment, not treated as a pass/fail per posting.

**Regression on prompt change.** Any prompt edit is re-run against the same
twenty-posting set before being trusted, and the acceptance criterion above is
re-checked. This gives FR-20's "re-runnable after a prompt change" an actual
gate, rather than only technical re-runnability. The set is fixed (not
resampled per change) so that results are comparable across prompt versions;
it is only reduced from "before" to "before *and* after" the moment there is
more than one recorded prompt version to compare.

## Consequences

*Favourable:*

- Closes an open design question before it is discovered as a gap mid-build.
- Fine-tuning being ruled out removes a whole category of future scope creep
  and cost from ever entering consideration for this project.
- The acceptance criterion gives "the scorer is trusted" a checkable
  definition instead of an operator's unstated feeling.
- The twenty-posting set does double duty (schema validity and judgement
  calibration), so this adds no new labeling burden beyond what D8 already
  required.

*Unfavourable, and accepted:*

- Twenty postings is a small sample; the 80% threshold is a heuristic, not a
  statistically powered figure. Acceptable because the cost of being wrong is
  a missed or wrongly-surfaced posting, not a safety or financial harm (design
  record §9.1, §2.1), and the operator reviews every published posting anyway
  (FR-25).
- A fixed regression set can go stale if the job market or the CV changes
  materially. Not mitigated here; revisit if scoring quality is ever observed
  to drift.
- Ruling out fine-tuning forecloses a path that could, in principle, produce a
  better-calibrated scorer. Accepted because nothing in this project's scale
  or budget supports building or maintaining that path.

## Control

This ADR does not unblock stage 3 — the CV is still the standing prerequisite
(SRS §13 item 1) — it removes the remaining process ambiguity so that once the
CV exists, model selection, prompting, and validation can proceed without a new
design decision along the way. The structural test tier can be built before the
CV arrives, since it needs no real model output.
