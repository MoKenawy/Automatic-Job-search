# ADR-0007: Scoring evaluation metric and score history

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 27 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | ADR-0006. Its model-selection and training decisions are carried forward unchanged and restated here; its testing decision is replaced |
| **Related** | [Design record](../job-discovery-pipeline-design.md) D4–D9, [SRS](../software-requirements-specification.md) §3.4 (FR-16–20), §5.1 (NFR-1), §13; ADR-0004, ADR-0005 |

---

## Context

ADR-0006 closed three questions for stage 3 — how a model is chosen, that it is
prompted rather than fine-tuned, and how it is tested. A review of it on 27 July
2026 found five gaps. Four are settled below; the fifth is recorded as open
because it needs discussion rather than a decision taken alone.

1. **The regression gate rests on data the schema cannot hold.** ADR-0006 §3
   compares results "across prompt versions", and FR-19 claims a prompt change
   is traceable. `postings.scored_by_model` records the model name only. `score`,
   `rationale`, `matched_skills` and `gaps` are single-valued columns, so FR-20's
   corpus-wide re-run overwrites exactly the output the gate would compare
   against. The gate was unexecutable as written.
2. **The premise for "no labeled corpus" is contradicted by the product.** Every
   FR-26 transition — Shortlist, Applied, Rejected — is an operator label,
   timestamped on a corpus retained indefinitely (D9). Labels accumulate whether
   or not anything is done with them.
3. **The acceptance criterion measures the wrong thing.** Agreement on 16 of 20
   is accuracy on an imbalanced binary problem, computed at a decision boundary
   that D7 says will itself be tuned on the same week's data, with no stated
   action if no candidate reaches it.
4. **Decoding is unspecified**, and §1's structural criterion may not
   discriminate between candidates at all.
5. **The validation population is drawn from postings that survived D6's regex
   filter**, whose recall is measured nowhere.

## Decision

### 1. Carried forward from ADR-0006, unchanged

**Model selection.** Criteria in order: structured-output reliability; a context
window holding CV, full description and taxonomy in one call; throughput on the
host GPU within NFR-1; licence, which matters only if weights or output are
redistributed. Method: run the twenty-posting structural check against each
shortlisted candidate once the CV exists. *One refinement:* where more than one
candidate passes cleanly, the tie is broken on §3's concordance figure rather
than by a longer bake-off. Whether the structural check can discriminate at all
is open — see O2.

**Training.** Prompting only. Fine-tuning is permanently out of scope, not
deferred: no fine-tuning pipeline or GPU-time budget exists, and the method is
disproportionate to fewer than a hundred postings a day. Reopening it requires a
new ADR. O1 below explores what to do with accumulated labels; none of the
options it lists is fine-tuning.

**Structural tests.** Unit tests over the response parser, independent of the CV
and of a running Ollama: valid JSON accepted; malformed JSON, missing fields and
out-of-range scores rejected rather than stored (FR-18). Buildable now.

### 2. Score history — a master row and an append-only history table

Scoring writes two rows, in one transaction:

| Table | Role |
|---|---|
| `postings` | Master. Keeps `score`, `matched_skills`, `gaps`, `rationale`, `scored_at`, `scored_by_model` as the *current* projection — a denormalised copy of the newest history row |
| `posting_scores` | Append-only. One row per scoring attempt, never updated, never deleted |

`posting_scores` carries, beyond the scoring output itself: `posting_id`,
`model`, `prompt_version`, `prompt_hash`, `cv_hash`, `run_id`, `scored_at`.

- **Master stays denormalised deliberately.** The list query orders on
  `postings.score` against the existing `ix_postings_triage_queue` index, and
  publication reads the same column. Neither the read path nor the interface
  changes; history is written for comparison, not for serving.
- **Prompt identity is two fields, not one.** `prompt_version` is a label the
  operator bumps; `prompt_hash` is a digest of the rendered prompt computed at
  run time. The digest catches the forgotten version bump, which is the common
  failure and the one that silently corrupts a comparison.
- **`cv_hash` answers "which CV produced this score".** The CV is expected to
  change; without it, scores from before and after a CV revision are
  indistinguishable and wrongly comparable.
- **Append-only is enforced by convention, not by a trigger.** Single-operator
  system; a database rule would be disproportionate. `raw_postings` sets the
  precedent (design §8).

This makes FR-19 true in substance rather than in name, and makes FR-20's
re-run non-destructive: the previous prompt's output survives its own
replacement, which is the precondition for §3's regression gate existing at all.

Implementation is an Alembic migration under `app/migrations/versions/`, and can
be built before the CV arrives.

### 3. Evaluation — pairwise concordance, with the threshold derived after it

**Why not agreement-on-20.** Accuracy on an imbalanced binary problem is passed
by a scorer carrying no information. If the operator would shortlist four of the
twenty, a model that rejects all twenty agrees on sixteen — 80%, exactly the
ADR-0006 bar — while ranking nothing. The metric has to be one such a scorer
fails.

**The metric.** *Pairwise concordance* between the model's score and the
operator's binary call: over every (shortlisted, rejected) pair of postings, the
proportion in which the shortlisted posting scored higher. Ties count as one
half. With five shortlisted and fifteen rejected, that is seventy-five pairwise
comparisons rather than twenty binary hits.

Three reasons this is the optimisation path for this system:

- **It is threshold-free.** Prompt quality and D7's publication threshold stop
  contaminating each other — the entanglement that made a failed agreement
  fixable by moving the cut rather than improving the scorer.
- **It measures what the score actually is.** The design record calls score "an
  ordering device for the published list", not a value the operator is expected
  to agree with. Concordance scores the ordering.
- **It resolves finely at n = 20.** Seventy-five comparisons instead of twenty,
  and it is unmoved by how many of the twenty the operator happened to like.

**Gate: concordance ≥ 0.85.** Occasional inversions are tolerable — the operator
reads every published posting anyway (FR-25) — but a scorer inverting a third of
its pairs is not ordering. Like ADR-0006's 80%, this is a declared heuristic, not
a powered figure. If the operator shortlists none or all of the twenty the
statistic is undefined and the set is resampled.

**The threshold is then derived, not guessed.** Once the gate passes, the initial
publication threshold is set just below the lowest score any operator-shortlisted
posting received — the cut that admits everything the operator wanted, accepting
whatever rejects come with it. This is where the asymmetry between the two error
types is spent: a false positive costs the operator seconds of reading, budgeted
by NFR-2; a false negative is never published, never seen, and unrecoverable.
Reported alongside: how many rejected postings sit above the cut. If that number
exceeds what NFR-2 tolerates, the answer is a better scorer, not a higher cut.
This gives D7's "60, to be tightened" a starting value derived from data.

**Regression on prompt change.** The same fixed twenty are re-scored and
concordance recomputed; a prompt that lowers it is not adopted. Every evaluated
prompt version lands in `posting_scores`, so this is auditable rather than
remembered.

**Iteration discipline.** Because the twenty are fixed and the prompt may be
iterated freely, concordance rising across many iterations is fitting the set,
not improving the scorer. `prompt_hash` makes the iteration count visible. Beyond
five recorded iterations against the same twenty, the set is treated as a
training set rather than a test set, and full trust waits on a held-out set — a
thing O1 is the route to, and which does not exist today.

**If no candidate reaches the gate**, in order: revise the prompt within the
iteration discipline above; try a larger model that still fits the host GPU under
NFR-3; or accept a lower gate, recorded in writing with its reason, and treat the
score as a weak ordering hint — meaning the threshold drops toward inclusive
publication and the operator absorbs more triage. Fine-tuning is not on this
list (§1).

### 4. Open questions

Recorded as open. None blocks §2 or the structural tests.

**O1 — Operator triage as the evaluation corpus.** Options to explore: keep the
fixed twenty; build a rolling evaluation set from accumulated Shortlist / Applied
/ Rejected labels; draw few-shot exemplars from labelled history; retrieve
nearest labelled neighbours via pgvector as prompt context (D4 bought PostgreSQL
partly for this). Three data-quality traps must be settled first, all of them
load-bearing:

- `reject_for_suppression()` writes the same `Rejected` status as an operator's
  own rejection, so a naive extraction conflates "not a role I want" with
  "employer blacklisted". Distinguishable via the employer's suppression flag,
  but only if handled deliberately.
- `New` is unreviewed, not negative. Treating it as a negative label poisons the
  set.
- Labels exist only for *published* postings, so an accumulated corpus can never
  speak about what the threshold or the title filter dropped — the same blind
  spot as O3.

**O2 — Decoding determinism, and what the structural criterion measures.** Two
sub-questions, unresolved:

- Ollama can constrain decoding to a JSON schema. With that on, every candidate
  passes ADR-0006 §1's first criterion, so it ranks nothing; with it off, the
  criterion measures a property that could simply have been forced. Either way
  it is doing less work than the ordering implies.
- Nothing sets temperature or a seed. At default temperature the same posting
  scores differently on consecutive runs, so a concordance change after a prompt
  edit cannot be attributed to the edit rather than to sampling. `posting_scores`
  makes this measurable directly: score the same twenty twice under one
  unchanged prompt and read the spread. That measurement is the cheapest way to
  settle the question, and it needs only the CV.

**O3 — The title pre-filter (D6): replace, demote, or drop.** D6 justifies the
regex as reducing model invocations, and that reduction has never been
quantified. NFR-1 budgets a few minutes for a run below one hundred postings; a
full scoring call carries CV, full description and taxonomy, and at a plausible
five to twenty seconds per posting on a local 7–8B, one hundred postings is
eight to thirty-three minutes. NFR-1 is therefore at risk *with* the filter and
likely breached without it — so this is a load question before it is a quality
question.

| | Option | Trade |
|---|---|---|
| A | Drop the filter; score everything | Removes the silent-drop blind spot; worst case for load |
| B | Status quo — regex gate | Cheapest; recall unmeasured |
| C | Model gate — title-only prompt, same model or a smaller one | Judgement instead of pattern; adds a short call per posting |
| D | Embedding gate — cosine of the title vector against the CV/target-role vector, in pgvector | Milliseconds per posting; reuses the capability D4 was chosen for |
| E | Regex demoted to availability fallback | An Ollama outage degrades to today's behaviour instead of stalling the run |

Direction to explore first is **D with E**: an embedding gate keeps FR-16's
"title only, never requirement analysis" constraint intact while replacing a
hand-written pattern with a measured similarity, and adds no scoring call. C is
the fallback if similarity separates the two classes poorly. Gating on the
*description* embedding rather than the title would change FR-16 and needs its
own decision.

Three measurements settle it, two of them available before the CV: the filter's
current drop rate, from the `title_filter_passed` column already in the schema;
the filter's recall, from a one-off scoring run over a sample of what it dropped;
and per-posting scoring latency on the host GPU.

## Consequences

*Favourable:*

- FR-19 becomes true in substance: the model, prompt and CV behind any stored
  score are recoverable, and FR-20's re-run no longer destroys its own baseline.
- Concordance cannot be passed by a degenerate all-reject scorer, and decouples
  prompt work from threshold work.
- D7's threshold gains a derived starting value in place of a guess, and the
  asymmetry between the two error types is spent deliberately.
- The three open questions are named, each with what would settle it, rather
  than being discovered mid-build.

*Unfavourable, and accepted:*

- Concordance on twenty postings is still a small sample; no confidence interval
  is claimed. Same posture and same justification as ADR-0006 — the cost of
  being wrong is a missed or wrongly-surfaced posting.
- Deriving the threshold from the same twenty that gate the scorer reuses one
  small sample twice. Accepted because D7 already treats the threshold as
  provisional.
- The history table grows without bound. At under a hundred postings a day and
  infrequent re-scores this is thousands of rows a year, trivial beside
  `raw_postings`.
- Stage 3 is left partly unspecified by three open questions. Accepted: none of
  them blocks the schema or the structural tests, which is the work available
  before the CV exists.

## Control

The CV remains the standing prerequisite (SRS §13 item 1) — this record does not
change that. Buildable before it arrives: the master/history schema and its
migration, the structural parser tests, and O3's drop-rate measurement. The
concordance gate, the derived threshold, and O2's determinism measurement all
wait on the CV.
