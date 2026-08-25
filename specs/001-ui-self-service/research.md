# Research & Open Decisions: Operator Self-Service

**Feature**: `001-ui-self-service` | **Date**: 21 July 2026

This document records the decisions that shape the plan and the open questions
(`[NEEDS CLARIFICATION]` in the spec) that should be resolved before or during
implementation. Each open question has a **recommended default** so work is not
blocked.

---

## Decisions taken

### D-A — The blacklist reuses `employers.suppressed`

**Superseded by [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md).**
`employers.suppressed` is still the blacklist flag (this half stands), but the
decision below (D-B) — reusing it as the *source for a materialised copy on
`postings`* — was reversed. Left unedited as the record of the original
reasoning.

`Employer.suppressed` already exists and is read nowhere. It becomes the blacklist
flag. No migration is needed for the column itself; a partial index on
`suppressed = true` supports the suppression query. This keeps the blacklist a
first-class employer property rather than a parallel list.

### D-B — Auto-rejection is an idempotent suppression pass

**Superseded by [ADR-0015](../../Docs/ADRs/0015-employer-level-suppression.md).**
There is no suppression pass and no materialised copy: suppression is derived
from `employers.suppressed` at read time by
[002-employer-suppression-derived](../002-employer-suppression-derived/spec.md)'s
visibility seam. `suppress_stage` is deleted. Left unedited below as the
record of the original reasoning.

Suppression runs as a stage (`suppress_stage`) after normalisation and before
scoring/publication, and also on demand when an employer is blacklisted. It sets
`status = 'rejected'` and `published = false` for every posting of a suppressed
employer. It is idempotent: re-running changes nothing already rejected. This
matches the pipeline's stage model (§7.1) and catches postings created mid-run.

### D-C — Runtime settings: database overrides environment

Environment/`.env` becomes the **seed** for defaults. An `app_settings` table
holds operator overrides. Resolution order at read time:
`app_settings value → environment default → code default`. Secrets and
restart-only settings are excluded from the table and remain env-only.

### D-D — Search profiles supersede `SEARCHES`; recorded in ADR-0005

The `SEARCHES` env list moves to a `search_profiles` table with per-row schedule
and enabled flag. This supersedes the relevant part of D14. Because it changes a
standing decision, it is recorded as **ADR-0005** before US4 is implemented — the
same discipline applied when Notion was superseded (ADR-0004).

### D-E — Per-profile scheduling

The scheduler reads enabled profiles and registers one APScheduler job per
profile at its configured time, replacing the single global 06:00 job. On profile
change (create/edit/enable/disable/delete) the scheduler reloads its jobs. Per-run
and per-source counts (§7.4) are preserved: each profile run still opens a `Run`
and records counts.

---

## Resolved questions

**All open questions below were resolved on 21 July 2026 by accepting the
recommended default.** Each is marked **DECISION (accepted)**.

### Q1 — What is "Experience" in a search profile? *(FR-016)* — DECISION (accepted): post-collection filter

JobSpy's `scrape_jobs` has **no first-class experience-level parameter**. Options:

- **(Recommended) Post-collection filter.** Store an experience level on the
  profile and filter/annotate after collection (and feed it into the stage-3
  scoring prompt). Robust across boards; no dependency on board-specific filters.
- Encode experience into the search term (e.g. "senior data engineer"). Simple but
  conflates with the role field and pollutes deduplication.
- LinkedIn-only experience filter via URL parameters. Board-specific and fragile.

**Impact if wrong**: low — the field can start as advisory metadata and become a
filter later without schema change.

### Q2 — Which settings are UI-editable vs. read-only vs. hidden? *(FR-019, FR-020)* — DECISION (accepted): the split below

Proposed split:

| Editable (operational) | Read-only in UI | Not shown (env-only) |
|---|---|---|
| results_per_search, hours_old, request_delay_seconds, publish_threshold, scoring_model, linkedin_fetch_description, title include/exclude patterns, proxies | timezone, web host/port | database_url |

**Recommendation**: adopt this split. `timezone` and bind host/port are
restart-affecting and shown read-only; `database_url` is infrastructure and hidden.
No current editable setting is a secret (after ADR-0004 there are no delivery
credentials), so Q's FR-020 concern resolves to "none".

### Q3 — Does "run now" for a profile run the full pipeline or collection only? — DECISION (accepted): full pipeline

**Recommendation**: full pipeline for that profile (collect → normalise →
suppress → score → publish), consistent with `run-all`, so the operator sees
publishable results immediately. Scored stages are skipped gracefully while stage
3/4 remain unimplemented.

### Q4 — Should scheduling be per-profile, or one schedule running all profiles? — DECISION (accepted): per-profile, defaulting to 06:00

The spec says each profile has "its own schedule" (FR-017). **Recommendation**:
per-profile schedule, defaulting a new profile to the current global time (06:00)
so behaviour is unchanged unless the operator sets otherwise.

### Q5 — Bulk update scope: selected rows only, or "all matching the filter"? — DECISION (accepted): selected rows only (v1)

**Recommendation**: selected rows only for v1 (explicit and safe). A future
"apply to all N matching" is deferred; it risks large unintended changes.

---

## Non-goals (confirmed out of scope)

- Authentication / multi-user (single operator, single machine).
- Editing infrastructure settings (database URL, ports) from the UI.
- Reinstating previously auto-rejected postings when a blacklist is removed.
- Automated application submission (unchanged from design §2.2).
