# Design Document — Data Model
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 21 July 2026 |
| **Status** | Approved |
| **Related** | [System Architecture](system-architecture.md), [SRS](../software-requirements-specification.md) |

---

## 1. Overview

The model has four entities. Two are landing/audit structures (`raw_postings`,
`runs`) and two are the domain (`employers`, `postings`). The design follows the
staging principle of design §7.2: raw collector output is retained verbatim and
append-only, and the deduplicated domain is derived from it, so the domain can be
rebuilt without re-collecting.

The store is PostgreSQL 16 with the pgvector extension enabled. JSON columns use
`JSONB`; the models declare a `JSON` variant for SQLite so the suite runs without
a database (Development Guide §4).

---

## 2. Entity–relationship diagram

```mermaid
erDiagram
    EMPLOYERS ||--o{ POSTINGS : "employs"
    RUNS ||--o{ RAW_POSTINGS : "produces"

    EMPLOYERS {
        int      id PK
        string   name
        string   normalised_name UK "suffixes stripped, descriptors kept"
        string   url "nullable, Indeed enrichment"
        string   logo_url "nullable"
        string   num_employees "nullable"
        string   revenue "nullable"
        text     description "nullable"
        bool     suppressed "exclude all postings from this employer"
        datetime created_at
    }

    RUNS {
        int      id PK
        datetime started_at "indexed"
        datetime finished_at "nullable"
        string   status "running | success | failed"
        int      collected_count
        int      deduplicated_count
        int      filter_passed_count "verdict as of last application"
        int      filter_rejected_count "verdict as of last application"
        int      scored_count
        int      published_count
        jsonb    counts_by_site "per-source counts, e.g. {indeed:30}"
        text     error "nullable"
    }

    RAW_POSTINGS {
        int      id PK
        int      run_id FK
        string   site "indexed"
        string   site_job_id "nullable, board id, not unique across boards"
        jsonb    payload "verbatim JobSpy row, all columns"
        datetime collected_at
    }

    POSTINGS {
        int      id PK
        string   fingerprint UK "sha256(employer|title|location)"
        int      employer_id FK
        string   title
        string   normalised_title
        string   location_raw "nullable, verbatim, not comparable across boards"
        string   country_code "nullable, ISO 3166-1 alpha-2, indexed"
        bool     is_remote
        text     description "nullable"
        date     date_posted "nullable, indexed"
        string   job_type "nullable"
        jsonb    sources "board -> {url, job_id, first_seen}"
        string   job_level "nullable, board-declared seniority"
        bool     title_filter_passed "nullable, tri-state, filter"
        bool     experience_filter_passed "nullable, tri-state, filter"
        int      score "nullable, indexed, stage 3"
        jsonb    matched_skills "nullable, stage 3"
        jsonb    gaps "nullable, stage 3"
        text     rationale "nullable, stage 3"
        datetime scored_at "nullable"
        string   scored_by_model "nullable, traceability"
        bool     published "indexed, stage 4"
        datetime published_at "nullable"
        string   status "new | shortlist | applied | rejected"
        datetime first_seen_at
        datetime last_seen_at
    }
```

**Note on relationships.** `postings` has no foreign key to `runs`. The link from
a posting back to the run(s) that surfaced it is intentionally indirect: a posting
is one real-world role that may be seen across many runs, whereas each
`raw_postings` row belongs to exactly one run. Provenance across runs is carried
in `postings.sources` and the `first_seen_at` / `last_seen_at` timestamps.

---

## 3. Entities

### 3.1 `employers`

Normalised employer records. `normalised_name` is the deduplication key — legal
suffixes removed, descriptor words retained (SRS FR-11) — and is unique. The
enrichment columns (`url`, `logo_url`, `num_employees`, `revenue`, `description`)
are populated opportunistically from Indeed, which carries company detail that
LinkedIn does not; they are filled only when empty and never overwritten.

`suppressed` excludes an employer entirely, including postings not yet seen. This
is distinct from posting-level rejection (§3.4).

### 3.2 `runs`

One row per pipeline execution. The count columns make each stage's throughput
auditable, and `counts_by_site` makes per-source decay visible — the observability
requirement of SRS NFR-4. `status` is `running` until a terminal transition; a row
left at `running` means the process died.

### 3.3 `raw_postings`

Append-only landing zone. `payload` holds the complete JobSpy row unchanged, so a
later decision to promote a field is a backfill over stored data rather than a
re-collection (SRS FR-8). `site_job_id` is the board's own identifier, retained
for diagnosis; it is not unique across boards and is not a key.

### 3.4 `postings`

One row per real-world role, keyed on `fingerprint`. Columns fall into groups:

- **Identity and provenance:** `fingerprint`, `employer_id`, `sources`.
- **Display and comparison:** `title`, `normalised_title`, `location_raw`,
  `country_code`, `is_remote`, `description`, `date_posted`, `job_type`. Note
  that `location_raw` is verbatim and **not comparable across boards** (one may
  render a city in Arabic, another in English); `country_code` is the comparable,
  parsed value and the one used in the fingerprint.
- **Filtering (ADR-0016):** `job_level`, `title_filter_passed`,
  `experience_filter_passed`. `job_level` is the board's own declared seniority,
  verbatim; where several collected rows fold into one posting it holds the
  lowest label among them, and it never holds an inference. The two verdict
  columns are **tri-state**, and the three states are different facts:

  | Value | Meaning |
  |---|---|
  | NULL | the criterion was not applied — never filtered, or disabled (empty pattern, absent or unreadable requested experience) |
  | TRUE | applied, and admitted — including admitted *because* the input was unknown |
  | FALSE | applied, and rejected |

  Whether a posting is rejected, and on which grounds, is derived from the pair
  rather than stored: criteria change routinely, so a recorded reason would be
  stale precisely when it is read. Written only by `pipeline/filter_stage.py`.
- **Scoring (stage 3):** `score`, `matched_skills`, `gaps`, `rationale`,
  `scored_at`, `scored_by_model`. All nullable until scored.
- **Publication and triage (stage 4):** `published`, `published_at`, `status`.

`status` is operator judgement only. It does **not** double as a suppression or
filtering mechanism: a blacklisted employer's postings (ADR-0015) and postings a
criterion turned away (ADR-0016) are withheld at read time through
`db/visibility.py`, never stamped. That separation is what makes both
reversible — lifting a blacklist or loosening a criterion restores the posting
with the triage status it already held. (The previous claim here, that `status`
doubled as the suppression mechanism, was falsified by ADR-0015 and is corrected
rather than left standing.)

---

## 4. Keys, indexes and constraints

| Table | Constraint / index | Purpose |
|---|---|---|
| `employers` | `normalised_name` unique | The deduplication key |
| `raw_postings` | `run_id` → `runs.id`, `ON DELETE CASCADE` | Deleting a run reclaims its landed rows |
| `raw_postings` | index on `site`, `site_job_id` | Diagnosis by board |
| `postings` | `fingerprint` unique | One record per real-world role |
| `postings` | `employer_id` → `employers.id` | Employer relationship |
| `postings` | index on `country_code`, `date_posted`, `score`, `published`, `status` | Filtering and ranking |
| `postings` | composite `ix_postings_triage_queue` (`published`, `status`, `score`) | The list view's primary query |

---

## 5. The fingerprint

The fingerprint is the model's most consequential derived value (SRS FR-9):

```
fingerprint = sha256( normalised_employer | normalised_title | location_token )
```

- `normalised_employer` — lowercased, accent- and punctuation-stripped, legal
  suffixes removed, bilingual names reduced to their Latin portion.
- `normalised_title` — lowercased and cleaned, but seniority and discipline
  markers retained.
- `location_token` — the ISO country code for on-site roles, `REMOTE` for remote
  roles, or `UNKNOWN` where the country cannot be resolved.

City is deliberately **not** an input: boards localise city names irreconcilably,
so including it would guarantee the duplicates the fingerprint exists to prevent
(design §7.3.1). `UNKNOWN` is kept distinct from `REMOTE` so that unresolved
locations remain countable rather than silently merging.

---

## 6. Lifecycle of a posting

```mermaid
stateDiagram-v2
    [*] --> Landed: stage 1 (raw_postings)
    Landed --> Deduplicated: stage 2 (upsert by fingerprint)
    Deduplicated --> Deduplicated: seen again (merge provenance)
    Deduplicated --> Scored: stage 3 (score, skills, gaps)
    Scored --> Published: stage 4 (score >= threshold)
    Published --> New: status on publication
    New --> Shortlist: operator
    Shortlist --> Applied: operator
    New --> Rejected: operator
    Shortlist --> Rejected: operator
    Rejected --> [*]: retained, never resurfaces
```

A posting seen again in a later run does not create a new record: its provenance
is merged and `last_seen_at` advanced, while scoring and triage state are left
undisturbed.

---

## 6a. Feature 001 additions (ADR-0005)

Two tables were added for operator self-service, plus active use of a dormant
column. Full detail in [specs/001-ui-self-service/data-model.md](../../specs/001-ui-self-service/data-model.md).

| Entity | Purpose |
|---|---|
| **`search_profiles`** | Named, individually scheduled job surveys; supersede the `SEARCHES` env list. Seeded from `SEARCHES` on migration. Each may carry its own `experience` and optional `title_include_pattern` / `title_exclude_pattern` (ADR-0018): NULL means the profile adds nothing, and the patterns apply in addition to the global ones |
| **`app_settings`** | Runtime-editable operational settings; resolution order `app_settings → env → code default` |
| `employers.suppressed` | Now the blacklist flag (was dormant): a suppressed employer's postings are hidden at read time and retained ([ADR-0015](../ADRs/0015-employer-level-suppression.md) — was "auto-rejected" under 001's original design, reversed) |
| `runs.profile_id` | Nullable FK attributing a run to the profile that triggered it |

## 7. Migrations

The schema is managed by Alembic. Migrations as at this version:

| Revision | Description |
|---|---|
| `ff6adc50ab28` | Initial schema; enables the `vector` extension up front |
| `dc0d779245f2` | Replaces Notion delivery fields with the `status` column (ADR-0004); backfills existing rows |
| `f35d01e216d8` | Partial index on suppressed employers (blacklist, US3) |
| `3374777f0db4` | Adds `search_profiles` and `app_settings`; `runs.profile_id`; seeds profiles from `SEARCHES` (ADR-0005) |

The `vector` extension is created in the first migration though no column uses it
yet, to avoid a future migration whose only purpose is the extension (design §14).
It is deliberately not dropped on downgrade, since dropping an extension is
database-wide.

*End of document.*
