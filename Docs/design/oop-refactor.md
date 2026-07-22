# Design Document — Paradigm Assignment and Object Model Refactor
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 2.0 |
| **Date** | 22 July 2026 |
| **Status** | Proposal |
| **Supersedes** | Revision 1 (whole-system OOP conversion), withdrawn — see §4 |
| **Related** | [System Architecture](system-architecture.md), [Data Model](data-model.md), [ADR-0004](../ADRs/0004-web-app-replaces-notion.md), [ADR-0005](../ADRs/0005-ui-config-and-db-search-profiles.md) |

---

## Summary

Revision 1 of this study proposed converting the whole codebase to an object
model. Running each component against the paradigm its problem actually has
shows that four paradigms are already in use here, and three of them are already
being applied correctly. What remains is a much smaller object-oriented change,
plus one configuration axis worth investing in — and one live bug found on the
way (§10).

Basis: 26 modules, 2,312 lines, branch `001-ui-self-service`.

---

## 1. What the refactor is actually fixing

The present design is a competent procedural one. It is not broken. Four
specific frictions in it are structural, and each is what an object model exists
to remove — these four, and no more, are the justification for the work in §4
through §11.

> **Friction 1 — global mutation as a configuration channel.**
> `store.apply_to_settings()` writes DB overrides onto the process-wide
> `Settings` singleton at the start of every run. Two runs cannot hold different
> configurations, and no test can assert a configuration without leaking it into
> the next test.

> **Friction 2 — the stage sequence is hard-coded.**
> `orchestrate._run()` names `run_collect`, `run_normalise` and `run_suppress`
> literally. Adding the unbuilt stages 3 and 4 means editing the orchestrator,
> the CLI, the six count columns on `runs`, and the health view.

> **Friction 3 — source differences live in an if-chain.**
> `collect_one()` branches on site name to decide `country_indeed`,
> `google_search_term` and `linkedin_fetch_description`. Each new board adds a
> branch to a function that already knows too much about four of them.

> **Friction 4 — domain rules sit in HTTP handlers.**
> `web/app.py` validates the status transition, stamps `last_seen_at`, sets
> `employer.suppressed` and then calls `suppress_employer`. The CLI cannot
> invoke those rules; the scheduler never learns that a profile's schedule
> changed.

---

## 2. Paradigm assignment

Paradigm is a property of a problem, not of a codebase. Run each component
against the question its own shape asks, and this system selects four different
answers — most of which it is already giving correctly. The refactor's scope is
exactly the set of components whose current paradigm does not match their
problem.

```mermaid
flowchart LR
  subgraph fp["FUNCTIONAL — already correct, do not touch"]
    direction TB
    n1["normalise/title.py<br/>normalise/employer.py"]
    n2["normalise/country.py<br/>normalise/fingerprint.py"]
    n3["web/queries.py<br/>read models to DTOs"]
  end

  subgraph oop["OBJECT-ORIENTED — the refactor's scope"]
    direction TB
    o1["Posting · Employer entities<br/>triage + suppression invariants"]
    o2["JobSource strategies<br/>per-board variance"]
    o3["Repositories · UnitOfWork"]
    o4["Application services<br/>+ domain events"]
  end

  subgraph dd["DATA-DRIVEN — highest remaining leverage"]
    direction TB
    d1["search_profiles rows"]
    d2["app_settings rows"]
    d3["title filter patterns (D6)"]
    d4["scoring prompt — not yet built"]
  end

  subgraph proc["PROCEDURAL — correct as is"]
    direction TB
    p1["__main__.py CLI"]
    p2["alembic migrations"]
  end

  subgraph dod["DATA-ORIENTED — ruled out by measurement"]
    direction TB
    x1["SoA / columnar layout · SIMD"]
    x2["ECS · sparse sets · ring buffers"]
  end
```

*Figure 1 — Paradigm assignment by component. Three of the five groups need no
work. That is the finding; revision 1 of this document proposed changes to all
of them.*

### 2.1 Why data-oriented design is the one that misses

Not a matter of taste. The project's own requirements close it, and the
arithmetic is not close.

| Budget line | Magnitude | Source |
|---|---|---|
| Target run wall-clock | ~10⁵ ms (minutes) | NFR-1 |
| Deliberate inter-request delay | 10,000 ms per request | §9.3, by design |
| LinkedIn per-posting description fetch | ~50 extra HTTP round trips | `linkedin_fetch_description` |
| Postgres round trips in stage 2 (N+1) | ~200 queries ≈ 200 ms | `normalise_stage.py:88,28` |
| **Actual CPU in normalisation, 100 rows** | **≈ 2.5 ms** | 2 regex passes + SHA-256 per row |

The transformation cost this system performs is roughly **0.001% of a run**.
Make it infinitely fast — free, zero — and nothing observable changes. Worse,
the binding constraint is a delay the system imposes *on purpose*: data-oriented
design optimises precisely the dimension being deliberately de-optimised for
collection etiquette.

Two further reasons it cannot pay here. In CPython the memory layout DOD depends
on is unreachable without leaving the object model entirely — every field is a
boxed `PyObject` behind a pointer. And §9.2 states the position outright:
publication is *"a database update over fewer than one hundred rows daily and is
not a throughput consideration."*

> **One honest exception, noted and dismissed.**
> `jobspy_client.py:50` calls `df.to_dict(orient="records")` — JobSpy hands back
> a columnar DataFrame and the first thing this code does is shred it into row
> dicts. That is the single genuinely anti-columnar line in the codebase. At
> ~100 rows it is correctly irrelevant, and `raw_postings` needs per-row JSONB
> anyway. It is recorded here only so that a future thousandfold increase in
> volume has a known place to start.

---

## 3. Target architecture

Ports and adapters, applied only to the object-oriented group from §2. The
domain layer holds entities, value objects and the abstract ports it needs; it
imports neither SQLAlchemy nor FastAPI nor JobSpy. The functional modules sit
alongside it and are called directly — they need no port, because a pure
function has no dependency to invert.

```mermaid
flowchart TB
  subgraph driving["Driving adapters — entry points"]
    direction LR
    cli["CliApplication<br/>typer commands"]
    web["WebApplication<br/>FastAPI routers"]
    sch["SchedulerDaemon<br/>APScheduler"]
  end

  subgraph appl["Application layer — use cases, transactions"]
    direction LR
    runner["PipelineRunner"]
    triage["TriageService"]
    black["BlacklistService"]
    profs["ProfileService"]
    setsvc["SettingsService"]
    reads["PostingQueryService"]
    bus["EventBus"]
  end

  subgraph core["Domain layer — no I/O, no framework imports"]
    direction LR
    ents["Entities<br/>Posting · Employer · Run · SearchProfile"]
    vos["Value objects<br/>Fingerprint · TriageStatus · SearchSpec · Assessment"]
    stages["PipelineStage hierarchy"]
    ports["Ports — abstract<br/>JobSource · Repository · UnitOfWork · SettingsProvider · Clock"]
  end

  subgraph pure["Pure functions — unchanged"]
    direction LR
    fns["normalise_title · normalise_employer<br/>parse_country · build_fingerprint"]
  end

  subgraph driven["Driven adapters — infrastructure"]
    direction LR
    jobspy["JobSpyGateway<br/>IndeedSource · LinkedInSource"]
    sql["SqlAlchemy repositories<br/>SqlAlchemyUnitOfWork"]
    conf["EnvSettingsProvider<br/>DatabaseSettingsProvider"]
    orm["ORM mapping to PostgreSQL 16"]
  end

  cli --> appl
  web --> appl
  sch --> appl
  appl --> core
  core --> pure
  jobspy -.implements.-> ports
  sql -.implements.-> ports
  conf -.implements.-> ports
  sql --> orm
```

*Figure 2 — Component and dependency view. Arrows point in the direction of
dependency. Nothing points out of the domain layer. The pure-function group is
called, never injected.*

---

## 4. Domain model

`Posting` becomes an aggregate root. Today it is an anaemic row: every rule
about it lives elsewhere — the born-rejected rule in `normalise_stage`, the
transition validation in a route handler, the suppression rule in
`suppress_stage`. Collecting those onto the entity is the single largest change
in this document, and the one that best justifies OOP: these are genuine
invariants attached to a noun.

```mermaid
classDiagram
  direction TB

  class Posting {
    <<Aggregate Root>>
    +PostingId id
    +Fingerprint fingerprint
    +EmployerRef employer
    +JobTitle title
    +Location location
    +Provenance sources
    +TriageStatus status
    +Assessment assessment
    +Publication publication
    +observe(SourceRecord, Clock) void
    +transition_to(TriageStatus) void
    +reject_for_suppression() bool
    +record(Assessment) void
    +publish_if_above(int) bool
    +merge_description(str) void
  }

  class Employer {
    <<Aggregate Root>>
    +EmployerId id
    +EmployerName name
    +CompanyProfile profile
    +bool suppressed
    +blacklist() EmployerBlacklisted
    +lift_blacklist() void
    +enrich_from(SourceRecord) void
  }

  class Run {
    <<Aggregate Root>>
    +RunId id
    +RunStatus status
    +SearchProfileId profile_id
    +StageTally tally
    +SourceCounts by_site
    +record(StageResult) void
    +succeed(Clock) void
    +fail(Exception, Clock) void
  }

  class SearchProfile {
    <<Aggregate Root>>
    +ProfileId id
    +str name
    +SearchSpec spec
    +Schedule schedule
    +bool enabled
    +to_spec() SearchSpec
    +reschedule(Schedule) ProfileRescheduled
    +enable() void
    +disable() void
  }

  class Fingerprint {
    <<Value Object>>
    +str employer
    +str title
    +str location
    +str digest
    +bool country_resolved
    +of(str, str, str, bool) Fingerprint$
  }

  class TriageStatus {
    <<enumeration>>
    NEW
    SHORTLIST
    APPLIED
    REJECTED
    +is_terminal() bool
    +can_move_to(TriageStatus) bool
  }

  class SearchSpec {
    <<Value Object>>
    +str term
    +str location
    +str country
    +bool is_remote
    +Sites sites
  }

  class Assessment {
    <<Value Object>>
    +int score
    +Skills matched
    +Skills gaps
    +str rationale
    +str model
    +datetime scored_at
  }

  class Provenance {
    <<Value Object>>
    +Sources by_site
    +with_(SourceRecord) Provenance
    +first_seen_on(str) datetime
  }

  class EmployerName {
    <<Value Object>>
    +str raw
    +str normalised
    +of(str) EmployerName$
  }

  class JobTitle {
    <<Value Object>>
    +str raw
    +str normalised
    +of(str) JobTitle$
  }

  class Location {
    <<Value Object>>
    +str raw
    +str country_code
    +bool is_remote
    +bool resolved
  }

  class Schedule {
    <<Value Object>>
    +int hour
    +int minute
    +str timezone
    +to_cron() CronTrigger
  }

  Posting "*" --> "1" Employer : employed by
  Posting *-- Fingerprint
  Posting *-- TriageStatus
  Posting *-- Assessment
  Posting *-- Provenance
  Posting *-- JobTitle
  Posting *-- Location
  Employer *-- EmployerName
  SearchProfile *-- SearchSpec
  SearchProfile *-- Schedule
  Run "*" --> "0..1" SearchProfile : triggered by
```

*Figure 3 — Domain class diagram. The value objects are thin wrappers whose
factories delegate to the existing pure functions: `EmployerName.of()` calls
`normalise_employer()`, `Fingerprint.of()` calls `build_fingerprint()`. No
normalisation logic is rewritten or moved — it is given a type.*

### 4.1 Rules that move onto the entity

| Rule | Lives today in | Moves to |
|---|---|---|
| A posting from a suppressed employer is born *rejected* (FR-007) | `normalise_stage.py:103` | `Posting` factory |
| Only the four known statuses are valid targets | `web/app.py:98` | `TriageStatus.can_move_to` |
| Rejecting a posting also un-publishes it | `suppress_stage.py:37` | `Posting.transition_to` |
| A description is backfilled but never overwritten | `normalise_stage.py:132` | `Posting.merge_description` |
| Enrichment fills gaps only, never overwrites | `normalise_stage.py:41-49` | `Employer.enrich_from` |
| Re-observing merges provenance, never duplicates | `normalise_stage.py:119-128` | `Provenance.with_` |

### 4.2 Explicitly out of scope

The normalisation logic itself. `normalise/title.py`, `employer.py`,
`country.py` and `fingerprint.py` are pure, deterministic, side-effect-free
functions over strings with no collaborators — functional programming applied to
a functional problem, and already correct.

**Revision 1 of this document proposed decomposing them into
`NormalisationRule` class chains. That was symmetry, not need, and it is
withdrawn.** These four modules are not modified in any phase.

---

## 5. Persistence data model

The refactor is behavioural, not a schema rewrite: five of the six tables keep
their columns exactly. Two changes are worth making because the object model
makes the current shape awkward, and both are additive.

```mermaid
erDiagram
    EMPLOYERS  ||--o{ POSTINGS      : employs
    RUNS       ||--o{ RAW_POSTINGS  : produces
    RUNS       ||--o{ RUN_STAGES    : "records (new)"
    SEARCH_PROFILES ||--o{ RUNS     : triggers

    EMPLOYERS {
        int      id PK
        string   name
        string   normalised_name UK "suffixes stripped, descriptors kept"
        string   url "nullable, Indeed enrichment"
        string   logo_url "nullable"
        string   num_employees "nullable"
        string   revenue "nullable"
        text     description "nullable"
        bool     suppressed "partial index where true"
        datetime created_at
    }

    POSTINGS {
        int      id PK
        string   fingerprint UK "sha256 of employer-title-country"
        int      employer_id FK
        string   title
        string   normalised_title
        string   location_raw "nullable, not comparable across boards"
        string   country_code "ISO 3166-1 alpha-2, nullable"
        bool     is_remote
        text     description "nullable"
        date     date_posted "nullable"
        string   job_type "nullable"
        jsonb    sources "provenance per board"
        bool     title_filter_passed "nullable, stage 3"
        int      score "nullable, stage 3"
        jsonb    matched_skills "nullable"
        jsonb    gaps "nullable"
        text     rationale "nullable"
        datetime scored_at "nullable"
        string   scored_by_model "nullable"
        bool     published
        datetime published_at "nullable"
        string   status "new-shortlist-applied-rejected"
        datetime status_changed_at "NEW - transition audit"
        datetime first_seen_at
        datetime last_seen_at
    }

    RAW_POSTINGS {
        int      id PK
        int      run_id FK
        string   site
        string   site_job_id "nullable, board-assigned"
        jsonb    payload "verbatim 34-column JobSpy row"
        datetime collected_at
    }

    RUNS {
        int      id PK
        datetime started_at
        datetime finished_at "nullable"
        string   status "running-success-failed"
        int      profile_id FK "nullable, null = run-all"
        jsonb    counts_by_site "per-source, detects silent decay"
        text     error "nullable"
    }

    RUN_STAGES {
        int      id PK
        int      run_id FK
        string   stage_name "collect-normalise-suppress-score-publish"
        int      sequence
        string   status "success-failed-skipped"
        int      input_count
        int      output_count
        int      duration_ms
        text     error "nullable"
    }

    SEARCH_PROFILES {
        int      id PK
        string   name UK
        string   term
        string   location "nullable"
        string   country
        bool     is_remote
        jsonb    sites
        string   experience "nullable, advisory"
        int      schedule_hour
        int      schedule_minute
        bool     enabled
        datetime created_at
        datetime updated_at
    }

    APP_SETTINGS {
        string   key PK "matches a Settings field"
        jsonb    value
        datetime updated_at
    }
```

*Figure 4 — Entity–relationship diagram, target state.*

| Change | Table | Rationale | Kind |
|---|---|---|---|
| `run_stages` replaces the six count columns on `runs` | `runs` → `run_stages` | Once a stage is a class, adding stage 3 should not require a migration for `scored_count`. One row per stage per run makes the tally polymorphic and sharpens the §7.4 decay signal — *which* stage is shrinking, not just the total. Deferred with phase 4; only worth it if stages 3–4 are being built. | additive |
| `status_changed_at` added to `postings` | `postings` | Transitions currently overload `last_seen_at`, which also means "a board surfaced this again". Two facts, one column. Separating them is a prerequisite for `Posting.transition_to()` being honest about what it stamps. | additive |
| `status` stays a string column | `postings` | Mapped to `TriageStatus` in the ORM layer, not by a native PostgreSQL enum type — which would make adding a state a locking DDL change for no gain. | unchanged |
| Rich declarative models, not imperative mapping | all | Keep `db/models.py` and add behaviour to those classes; value objects become SQLAlchemy composites. See §8. | decided |

---

## 6. Collection — sources as strategies

Each board becomes a class holding its own quirks. This is behavioural variance
between boards, which is what polymorphism is for — as distinct from the string
transformations in §4, which are data variance and stay functional.

```mermaid
classDiagram
  direction LR

  class JobSource {
    <<abstract · Port>>
    +str name
    +fetch(SearchSpec, RuntimeConfig) SourceOutcome
    #build_request(SearchSpec, RuntimeConfig) dict*
    #parse(DataFrame) SourceRecords
    #on_failure(Exception) SourceOutcome
  }

  class JobSpySource {
    <<abstract>>
    -JobSpyGateway gateway
    +fetch(SearchSpec, RuntimeConfig) SourceOutcome
    #parse(DataFrame) SourceRecords
  }

  class IndeedSource {
    +str name = "indeed"
    #build_request(SearchSpec, RuntimeConfig) dict
  }
  class LinkedInSource {
    +str name = "linkedin"
    #build_request(SearchSpec, RuntimeConfig) dict
  }
  class GoogleSource {
    +str name = "google"
    #build_request(SearchSpec, RuntimeConfig) dict
  }

  class JobSpyGateway {
    <<Adapter>>
    +scrape(dict) DataFrame
    -throttle(float) void
    -coerce_nulls(DataFrame) DataFrame
  }

  class SourceRegistry {
    <<Registry>>
    -sources Map
    +register(JobSource) void
    +for_spec(SearchSpec) SourceList
    +known_names() Names
  }

  class CollectionService {
    -SourceRegistry registry
    +collect(Specs, RuntimeConfig) CollectionResult
  }

  class SourceOutcome {
    <<Value Object>>
    +str site
    +SourceRecords records
    +str error
    +int count
    +bool succeeded
  }

  class CollectionResult {
    <<Value Object>>
    +SourceOutcomes outcomes
    +int total
    +SourceCounts counts_by_site
    +Errors errors
    +merge(CollectionResult) CollectionResult
  }

  JobSource <|-- JobSpySource
  JobSpySource <|-- IndeedSource
  JobSpySource <|-- LinkedInSource
  JobSpySource <|-- GoogleSource
  JobSpySource --> JobSpyGateway : delegates
  SourceRegistry o-- JobSource
  CollectionService --> SourceRegistry
  CollectionService ..> CollectionResult : produces
  JobSource ..> SourceOutcome : produces
  CollectionResult o-- SourceOutcome
```

*Figure 5 — Strategy + Adapter + Registry over the collectors.
`JobSpyGateway.throttle()` is where the missing `request_delay_seconds` belongs
— see §10. The gateway is the only object that knows a network call is being
made, so it is the only correct home for pacing it.*

> **The payoff is testability, not extensibility.**
> There will probably never be twenty boards. But a `FakeSource` returning a
> canned frame lets stage 1 be tested without monkey-patching
> `jobspy.scrape_jobs`, which is what `test_collect.py` must do today.

---

## 7. The pipeline — stages as objects

A composite of template methods, with a batch-in / batch-out contract. This is
the one place the dataflow framing genuinely contributes: a stage is a stateless
transform between durable buffers, and the buffers are database tables rather
than memory because the requirement is re-runnability, not throughput.

```mermaid
classDiagram
  direction TB

  class PipelineStage {
    <<abstract>>
    +str name
    +execute(PipelineContext) StageResult
    #run(PipelineContext) StageOutput*
    #should_skip(PipelineContext) bool
    #on_error(Exception) StageResult
  }

  class CollectStage {
    -CollectionService collector
    #run(PipelineContext) StageOutput
  }
  class NormaliseStage {
    -EmployerResolver employers
    #run(PipelineContext) StageOutput
  }
  class SuppressStage {
    #run(PipelineContext) StageOutput
  }
  class ScoreStage {
    <<planned>>
    -TitleFilter filter
    -Scorer scorer
    #run(PipelineContext) StageOutput
  }
  class PublishStage {
    <<planned>>
    #run(PipelineContext) StageOutput
  }

  class Pipeline {
    <<Composite>>
    -StageList stages
    -EventBus events
    +execute(PipelineContext) RunReport
    +with_stage(PipelineStage) Pipeline
  }

  class PipelineContext {
    +Run run
    +Specs specs
    +RuntimeConfig config
    +UnitOfWork uow
    +Clock clock
  }

  class StageResult {
    <<Value Object>>
    +str stage
    +str status
    +int input_count
    +int output_count
    +int duration_ms
    +str error
  }

  class RunReport {
    <<Value Object>>
    +RunId run_id
    +StageResults results
    +bool succeeded
  }

  class PipelineRunner {
    <<Application Service>>
    -Pipeline pipeline
    -UnitOfWorkFactory uows
    -SettingsResolver settings
    +run_profile(ProfileId) RunReport
    +run_all_enabled() RunReport
  }

  PipelineStage <|-- CollectStage
  PipelineStage <|-- NormaliseStage
  PipelineStage <|-- SuppressStage
  PipelineStage <|-- ScoreStage
  PipelineStage <|-- PublishStage
  Pipeline o-- PipelineStage
  Pipeline ..> RunReport : produces
  PipelineStage ..> StageResult : produces
  RunReport o-- StageResult
  PipelineRunner --> Pipeline
  PipelineRunner ..> PipelineContext : assembles
```

*Figure 6 — Pipeline, stages and the run context. The context carries a `Clock`
port so `first_seen_at` and the idempotency of re-normalisation are
deterministically testable, rather than calling `datetime.now(UTC)` inside the
stage. `track_run` dissolves into `Pipeline.execute()`.*

> **Where set-based thinking does pay.**
> `NormaliseStage` currently issues two queries per raw row — a fingerprint
> lookup and an employer lookup — roughly 200 round trips per run. Batching them
> into one `IN` query each is the only place in this codebase where "think in
> batches, not rows" buys a measurable improvement. It is ~200 ms, so do it
> while rewriting the stage; do not do it for its own sake.

---

## 8. Persistence — repositories and unit of work

Today `run_collect`, `run_normalise` and `run_suppress` each call
`session.commit()` themselves, so a failure in stage 2 leaves stage 1's commit
standing. That is defensible for a staging pipeline — but it should be a
decision the orchestrator makes, not one each stage makes for itself.

```mermaid
classDiagram
  direction LR

  class UnitOfWork {
    <<abstract · Port>>
    +PostingRepository postings
    +EmployerRepository employers
    +RunRepository runs
    +ProfileRepository profiles
    +SettingRepository settings
    +__enter__() UnitOfWork
    +__exit__(exc) void
    +commit() void
    +rollback() void
    +collect_events() DomainEvents
  }

  class SqlAlchemyUnitOfWork {
    -Session session
    -SessionFactory factory
    +commit() void
    +rollback() void
  }

  class InMemoryUnitOfWork {
    <<test double>>
    +commit() void
  }

  class Repository~T~ {
    <<abstract · Port>>
    +get(id) T
    +add(T) void
    +list() Entities
  }

  class PostingRepository {
    <<abstract>>
    +by_fingerprints(Digests) PostingMap
    +for_employer(EmployerId) Postings
    +not_rejected_for_suppressed() Postings
    +touched_in(RunId) Postings
  }

  class EmployerRepository {
    <<abstract>>
    +by_normalised_names(Names) EmployerMap
    +get_or_create(EmployerName) Employer
    +suppressed() Employers
  }

  class RunRepository {
    <<abstract>>
    +open(ProfileId) Run
    +recent(int) Runs
  }

  class SqlPostingRepository {
    -Session session
  }
  class FakePostingRepository {
    <<test double>>
    -dict rows
  }

  UnitOfWork <|-- SqlAlchemyUnitOfWork
  UnitOfWork <|-- InMemoryUnitOfWork
  Repository <|-- PostingRepository
  Repository <|-- EmployerRepository
  Repository <|-- RunRepository
  PostingRepository <|-- SqlPostingRepository
  PostingRepository <|-- FakePostingRepository
  UnitOfWork o-- PostingRepository
  UnitOfWork o-- EmployerRepository
  UnitOfWork o-- RunRepository
```

*Figure 7 — Repository + Unit of Work. Note the plural lookups —
`by_fingerprints`, `by_normalised_names`. Designing the repository interface
batch-first is what makes the §7 fix natural rather than an optimisation bolted
on later.*

> **Decided — keep declarative models.**
> Imperative mapping (`registry.map_imperatively()`) would make the domain
> layer's "no framework imports" claim literally true, at the cost of a mapping
> file per entity. For a single-operator system with one database that is
> ceremony. Keep `db/models.py` as declarative classes and add behaviour to
> them; express value objects as SQLAlchemy composites. Revisit only if a second
> persistence target ever appears.

---

## 9. Configuration — a resolution chain, not a mutated global

This removes the hazard in friction 1. The ADR-0005 note calls the current
global mutation "acceptable for a single-operator system", which is true — and
is exactly the kind of acceptance an explicit resolution chain lets you stop
making.

```mermaid
classDiagram
  direction LR

  class SettingsProvider {
    <<abstract · Port>>
    +SettingsProvider successor
    +resolve(str key) Any
    #lookup(str key) Any*
  }

  class DatabaseSettingsProvider {
    -SettingRepository repo
    #lookup(str key) Any
  }
  class EnvironmentSettingsProvider {
    -Settings pydantic_settings
    #lookup(str key) Any
  }
  class DefaultSettingsProvider {
    #lookup(str key) Any
  }

  class SettingsResolver {
    -SettingsProvider head
    +snapshot() RuntimeConfig
    +editable_keys() Keys
  }

  class RuntimeConfig {
    <<Value Object · immutable>>
    +int results_per_search
    +int hours_old
    +float request_delay_seconds
    +int publish_threshold
    +str scoring_model
    +bool linkedin_fetch_description
    +TitleFilterSpec title_filter
    +Proxies proxies
    +with_overrides(dict) RuntimeConfig
  }

  class SettingsService {
    <<Application Service>>
    -SettingsResolver resolver
    -SettingRepository repo
    +effective() RuntimeConfig
    +save(dict) RuntimeConfig
    +coerce_form(dict) dict
  }

  SettingsProvider <|-- DatabaseSettingsProvider
  SettingsProvider <|-- EnvironmentSettingsProvider
  SettingsProvider <|-- DefaultSettingsProvider
  SettingsProvider --> SettingsProvider : successor
  SettingsResolver --> SettingsProvider : head of chain
  SettingsResolver ..> RuntimeConfig : builds
  SettingsService --> SettingsResolver
```

*Figure 8 — Chain of Responsibility over configuration sources. The chain
encodes the ADR-0005 resolution order structurally: database override →
environment/.env → code default. A `RuntimeConfig` snapshot is taken once when a
run opens and passed down the pipeline, so a run's configuration is fixed for
its duration.*

---

## 10. The data-driven surface — and a hole in it

ADR-0005 already moved behaviour out of code and into database rows: schedules,
sites, search terms, thresholds, title filters. That is textbook data-driven
design, it is why UI self-service was buildable at all, and it is the axis with
the most remaining leverage — the only one that lets the system's behaviour
change without touching code.

It also has a specific failure mode that neither OOP nor FP has: **configuration
that drives nothing fails silently, because no compiler checks that a setting
reaches a call site.** Auditing all nine editable keys against their consumers
found one.

| Editable key | Declared | Validated | Consumed by | State |
|---|---|---|---|---|
| `results_per_search` | ✓ | ✓ positive | `collect_one` → `results_wanted` | live |
| `hours_old` | ✓ | ✓ positive | `collect_one` → `hours_old` | live |
| `linkedin_fetch_description` | ✓ | ✓ | `collect_one` → kwarg | live |
| `proxies` | ✓ | ✓ | `collect_one` → `proxies` | live |
| `request_delay_seconds` | ✓ `config.py:51` | ✓ non-negative | **nothing — never passed** | **broken** |
| `publish_threshold` | ✓ | ✓ 0–100 | stage 4 — unbuilt | pending |
| `scoring_model` | ✓ | ✓ | stage 3 — unbuilt | pending |
| `title_include_pattern` | ✓ | ✓ | stage 3 — unbuilt | pending |
| `title_exclude_pattern` | ✓ | ✓ | stage 3 — unbuilt | pending |

> **Bug — the primary rate-limit remedy does nothing.**
> `request_delay_seconds` is declared at `config.py:51`, validated at
> `store.py:41-46`, listed in `EDITABLE_KEYS`, rendered on the settings page and
> covered by two tests — and it is never passed to anything. It does not appear
> in the `scrape_jobs` kwargs built by `collect_one()`, and the installed
> JobSpy's signature has no delay parameter at all.
>
> Per §9.3, raising this delay is *the first remedy* when a board begins
> restricting access, which is the top item in the risk register. The primary
> documented mitigation for the primary operational risk is inert. It belongs in
> `JobSpyGateway.throttle()` (§6), sleeping between calls in this application's
> own code rather than hoping the library honours it.

### 10.1 Closing the class of bug, not just the instance

One test makes this category impossible to reintroduce — assert that every key
in `EDITABLE_KEYS` is either read by a named consumer or explicitly registered
as pending against an unbuilt stage. It is the data-driven equivalent of a
compiler warning for an unused parameter.

### 10.2 Where to extend the data-driven surface next

- The stage 3 scoring prompt should be an `app_settings` row, not a Python
  string literal — prompt iteration is the highest-frequency change a scorer
  will ever see, and the design already requires `scored_by_model` so a prompt
  change stays traceable.
- The D6 title filter is already data. Keep it that way; resist compiling it
  into a `TitleFilter` class hierarchy.
- Anything a single operator will want to tune weekly belongs here. Anything
  with an invariant attached to it belongs in §4.

---

## 11. Application services and domain events

Web routes and CLI commands become adapters that translate a request into a
service call. The same `BlacklistService.blacklist()` serves an HTMX post and a
future `python -m app blacklist` command.

```mermaid
classDiagram
  direction TB

  class TriageService {
    -UnitOfWorkFactory uows
    +set_status(PostingId, TriageStatus) Posting
    +set_status_bulk(Ids, TriageStatus) int
  }
  class BlacklistService {
    -UnitOfWorkFactory uows
    -EventBus events
    +blacklist(EmployerId) int
    +lift(EmployerId) void
    +listing() BlacklistRows
  }
  class ProfileService {
    -UnitOfWorkFactory uows
    -EventBus events
    +create(ProfileInput) SearchProfile
    +update(ProfileId, ProfileInput) SearchProfile
    +set_enabled(ProfileId, bool) SearchProfile
    +delete(ProfileId) void
  }
  class PostingQueryService {
    <<read model · functional>>
    -Session session
    +list(TriageFilter) PostingSummaries
    +detail(PostingId) PostingDetail
    +totals() Totals
    +source_health(int) SourceHealth
  }

  class EventBus {
    -handlers Map
    +subscribe(EventType, Handler) void
    +publish(DomainEvent) void
  }

  class DomainEvent {
    <<abstract>>
    +datetime occurred_at
  }
  class EmployerBlacklisted {
    +EmployerId employer_id
  }
  class ProfileRescheduled {
    +ProfileId profile_id
    +Schedule schedule
  }
  class RunCompleted {
    +RunId run_id
    +RunReport report
  }

  class SuppressPostingsHandler {
    +handle(EmployerBlacklisted) void
  }
  class ReloadSchedulerHandler {
    +handle(ProfileRescheduled) void
  }

  DomainEvent <|-- EmployerBlacklisted
  DomainEvent <|-- ProfileRescheduled
  DomainEvent <|-- RunCompleted
  EventBus --> DomainEvent : dispatches
  BlacklistService ..> EmployerBlacklisted : raises
  ProfileService ..> ProfileRescheduled : raises
  EmployerBlacklisted --> SuppressPostingsHandler
  ProfileRescheduled --> ReloadSchedulerHandler
```

*Figure 9 — Services, events and subscribers.*

> **This fixes a live gap, not a hypothetical one.**
> `scheduler.py` registers one APScheduler job per enabled profile at process
> start and never reloads. Its own docstring says "on profile change the jobs
> are reloaded" — nothing does that. Editing a schedule at `/profiles` has no
> effect until the container restarts. `ProfileRescheduled →
> ReloadSchedulerHandler` is the seam that closes it, and `_register_jobs` is
> already written to be re-callable.

---

## 12. Behaviour

Two lifecycles currently enforced by scattered `if` statements, and the two
sequences that exercise most of the design.

### 12.1 Posting triage lifecycle

```mermaid
stateDiagram-v2
    direction LR
    [*] --> New : first observed
    [*] --> Rejected : employer already blacklisted (FR-007)

    New --> Shortlist : operator triage
    New --> Applied : operator triage
    New --> Rejected : operator triage / employer blacklisted

    Shortlist --> Applied : operator triage
    Shortlist --> New : operator triage
    Shortlist --> Rejected : operator triage / employer blacklisted

    Applied --> Rejected : operator triage / employer blacklisted
    Applied --> Shortlist : operator triage

    Rejected --> [*] : terminal — retained, never resurfaces (D9)

    note right of Rejected
      Entering Rejected also clears
      published. Lifting a blacklist
      does NOT reinstate (FR-011).
    end note
```

*Figure 10 — Posting triage lifecycle.*

**Decision needed.** The current code permits any status to be set from any
other, including out of Rejected. Making Rejected terminal is a behavioural
change, not a refactor — confirm before implementing.

### 12.2 Run lifecycle

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Running : Pipeline.execute opens the run
    Running --> Success : every stage returned
    Running --> Failed : a stage raised — error retained, re-raised
    Running --> Running : stage recorded, next stage begins
    Success --> [*]
    Failed --> [*]

    note right of Running
      A run left at Running means the
      process died outright. That is
      itself the diagnostic signal.
    end note
```

*Figure 11 — Run lifecycle.*

### 12.3 Scheduled run of one search profile

```mermaid
sequenceDiagram
    autonumber
    participant Sch as SchedulerDaemon
    participant PR as PipelineRunner
    participant SR as SettingsResolver
    participant UoW as SqlAlchemyUnitOfWork
    participant P as Pipeline
    participant CS as CollectStage
    participant GW as JobSpyGateway
    participant NS as NormaliseStage
    participant SS as SuppressStage
    participant Bus as EventBus

    Sch->>PR: run_profile(profile_id)
    PR->>SR: snapshot()
    SR-->>PR: RuntimeConfig (db, env, default)
    PR->>UoW: begin()
    UoW->>UoW: runs.open(profile_id) → Run[Running]
    PR->>P: execute(PipelineContext)

    P->>CS: execute(ctx)
    loop each spec × each site
        CS->>GW: scrape(request)
        GW->>GW: throttle(config.request_delay_seconds)
        GW-->>CS: DataFrame or error
    end
    CS->>UoW: raw_postings.add_all(...)
    CS-->>P: StageResult(collect, out=87)

    P->>NS: execute(ctx)
    NS->>NS: build_fingerprint(...) — pure function
    NS->>UoW: postings.by_fingerprints(all digests)
    NS->>UoW: employers.by_normalised_names(all names)
    alt not seen before
        NS->>NS: Posting(...) — born Rejected if employer suppressed
    else seen before
        NS->>NS: posting.observe(record, clock)
    end
    NS-->>P: StageResult(normalise, in=87, out=54)

    P->>SS: execute(ctx)
    SS->>UoW: postings.not_rejected_for_suppressed()
    SS->>SS: posting.reject_for_suppression()
    SS-->>P: StageResult(suppress, out=3)

    P->>UoW: commit()
    P->>Bus: publish(RunCompleted)
    P-->>PR: RunReport(success)
```

*Figure 12 — Scheduled run. Two changes from today are visible: the batched
repository lookups replacing per-row queries, and `throttle()` finally consuming
the setting from §10.*

### 12.4 Operator blacklists an employer

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant W as WebApplication
    participant BS as BlacklistService
    participant UoW as UnitOfWork
    participant E as Employer
    participant Bus as EventBus
    participant H as SuppressPostingsHandler

    Op->>W: POST /employers/17/blacklist
    W->>BS: blacklist(EmployerId(17))
    BS->>UoW: begin()
    UoW->>UoW: employers.get(17)
    BS->>E: blacklist()
    E-->>BS: EmployerBlacklisted(17)
    BS->>UoW: commit()
    BS->>Bus: publish(EmployerBlacklisted)
    Bus->>H: handle(event)
    H->>UoW: postings.for_employer(17)
    loop each not-yet-rejected posting
        H->>H: posting.reject_for_suppression()
    end
    H->>UoW: commit()
    H-->>Bus: 12 postings rejected
    BS-->>W: BlacklistResult(rejected=12)
    W-->>Op: 303 to return_to, flash "12 postings rejected"
```

*Figure 13 — Blacklist an employer. Compare with today: the route sets
`employer.suppressed = True`, commits, calls `suppress_employer(db, id)`
directly, and redirects without telling the operator how many postings were
affected.*

---

## 13. Module-to-paradigm map

Every existing module, its paradigm, and its disposition. Six modules totalling
340 lines are explicitly untouched.

| Module | Lines | Paradigm | Disposition |
|---|---|---|---|
| `normalise/fingerprint.py` | 65 | functional | unchanged — wrapped by `Fingerprint` VO |
| `normalise/employer.py` | 82 | functional | unchanged |
| `normalise/title.py` | 39 | functional | unchanged |
| `normalise/country.py` | 114 | functional | unchanged |
| `web/queries.py` | 115 | functional | rename to `PostingQueryService`; DTOs already correct |
| `db/models.py` | 291 | object | keep classes, add behaviour + `status_changed_at` |
| `collect/jobspy_client.py` | 118 | object | `JobSpyGateway` · `IndeedSource` · `LinkedInSource` |
| `config.py` | 89 | object | `EnvironmentSettingsProvider` · `RuntimeConfig` |
| `db/session.py` | 37 | object | `SqlAlchemyUnitOfWork` · `UnitOfWorkFactory` |
| `pipeline/collect_stage.py` | 89 | object | `CollectStage` |
| `pipeline/normalise_stage.py` | 144 | object | `NormaliseStage` — rules move onto entities, queries batched |
| `pipeline/suppress_stage.py` | 63 | object | `SuppressStage` · `SuppressPostingsHandler` |
| `pipeline/run.py` | 50 | object | absorbed into `Pipeline.execute` |
| `pipeline/orchestrate.py` | 56 | object | `PipelineRunner` · `Pipeline` · `PipelineContext` |
| `settings_store/store.py` | 150 | data-driven | `SettingsService` + provider chain |
| `settings_store/profiles.py` | 139 | data-driven | `ProfileService` · `ProfileRepository` |
| `scheduler.py` | 51 | object | `SchedulerDaemon` · `ReloadSchedulerHandler` |
| `web/app.py` | 346 | object | routers only — delegate to services |
| `__main__.py` | 187 | procedural | stays procedural; command bodies delegate to services |

---

## 14. Sequencing

A phase 0 that is not a refactor at all, then four phases each independently
shippable and each leaving the suite green. No phase requires the next to be
worth doing — which is the property that makes it safe to stop partway.

| Phase | Work | Unlocks | Verdict |
|---|---|---|---|
| **0** | Pass `request_delay_seconds` to a real sleep between collector calls. Add the "every editable key has a consumer" test. Fix the scheduler reload directly if phase 5 is not being done. | The documented remedy for board restriction actually works. | **do first** |
| **1** | Value objects and entity behaviour. `Fingerprint`, `TriageStatus`, `EmployerName`, `JobTitle` as thin types over the existing pure functions; move the six rules from §4.1 onto `Posting` and `Employer`. | Domain rules unit-testable without a database. | recommended |
| **2** | Repositories and Unit of Work behind the existing stage functions, with batch-first lookups. | Fakes replace SQLite in tests; the N+1 disappears. | recommended |
| **3** | Settings chain and `RuntimeConfig`. Delete `apply_to_settings` and thread the snapshot through. | Kills global mutation. Prerequisite for any concurrency. | recommended |
| **4** | Stage classes, `Pipeline`, `run_stages` table. | Stages 3 and 4 become additions, not edits. | only if scoring is being built |
| **5** | Application services, event bus, thin routers. | Scheduler reload; web and CLI reach identical behaviour. | only if a second entry point matters |

> **Revised accounting.**
> Revision 1 estimated 26 modules → ~55 and 2,312 lines → ~3,000–3,400. With the
> normalisers out of scope and phases 4–5 made conditional, phases 0–3 come to
> roughly **26 modules → ~38, and ~2,312 lines → ~2,650** — about 15% more code,
> concentrated entirely on the four frictions in §1. That is a proportionate
> change for a 2,300-line single-operator system. The previous estimate was not.

---

## 15. Pattern register

| Pattern | Applied to | Problem it removes | Phase |
|---|---|---|---|
| Value Object | `Fingerprint`, `TriageStatus`, `RuntimeConfig` | Primitive obsession; validity re-checked at every use site | 1 |
| Aggregate / rich entity | `Posting`, `Employer` | Invariants scattered across three layers | 1 |
| Repository | Posting / Employer / Run / Profile | Queries inlined in business logic; N+1 lookups | 2 |
| Unit of Work | `SqlAlchemyUnitOfWork` | Each stage deciding its own commit boundary | 2 |
| Chain of Responsibility | `SettingsProvider` only | Global mutation as a config channel | 3 |
| Strategy | `JobSource` hierarchy | Site-specific branching in `collect_one` | 3 |
| Adapter | `JobSpyGateway` | Direct `scrape_jobs` coupling; forces monkey-patching in tests | 3 |
| Registry | `SourceRegistry` | `WORKING_SITES` validated in three places | 3 |
| Template Method | `JobSource.fetch`, `PipelineStage.execute` | Repeated try/except/count/log scaffolding | 4 |
| Composite | `Pipeline` | Hard-coded stage sequence | 4 |
| Facade / Application Service | `TriageService`, `BlacklistService`, … | Domain rules reachable only over HTTP | 5 |
| Observer / domain events | `EventBus` + handlers | Scheduler never reloading | 5 |
| **— none, deliberately** | `normalise/*` | Pure functions need no pattern | — |

Phases 0–3 account for eight of these. The remaining four are contingent on
stages 3 and 4 being built. If scoring and publication are shelved, stop after
phase 3 and leave `orchestrate.py` exactly as it is.
