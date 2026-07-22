# ADR-0005: UI-driven configuration and database-backed search profiles

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 21 July 2026 |
| **Decision maker** | Mohammed |
| **Supersedes** | Part of D14 (searches in `.env`); the static-configuration assumption in the technology stack |
| **Related** | ADR-0004, feature `001-ui-self-service` |

---

## Context

Configuration is currently supplied entirely by environment / `.env` and loaded
into an immutable module singleton at process start (`settings = Settings()`).
Changing anything — the publish threshold, the request delay, the set of searches —
means editing a file and restarting the containers.

Feature 001 requires the operator to configure the system from the interface
(ADR-0004's single surface), including operational settings and per-search
schedules with their own role, experience, location, and sites. An immutable
start-time singleton cannot satisfy that, and the `SEARCHES` environment list
cannot carry per-row schedule and enabled state or be edited individually.

## Decision

**Operational configuration and search definitions move into the database, edited
through the interface. Environment configuration becomes the seed for defaults,
not the live source of truth.**

Concretely:

1. **`app_settings` table** holds runtime-editable operational values. Resolution
   order on read is `app_settings → environment/.env default → code default`.
2. **`search_profiles` table** replaces the `SEARCHES` environment list. Each
   profile is a named search with its own sites, remote flag, experience, and
   schedule, and can be individually enabled, disabled, edited, deleted, and run
   on demand. On migration, the current `SEARCHES` value is seeded as profiles so
   behaviour is unchanged.
3. **Per-profile scheduling** replaces the single global daily job: the scheduler
   registers one job per enabled profile at its configured time and reloads when
   profiles change.

**Excluded from the UI and kept environment-only:** the database connection
(`DATABASE_URL`) and bind settings (`WEB_HOST`/`WEB_PORT`), which are
infrastructure and/or require a restart. `TIMEZONE` is shown read-only. No editable
setting is a secret (after ADR-0004 there are no delivery credentials).

## Consequences

*Favourable:*

- The operator configures everything from the single surface (ADR-0004), no file
  editing or restart.
- Per-search schedules become possible — different roles can run at different
  times.
- Settings changes take effect on the next run without a restart.
- `.env` remains a valid bootstrap: a fresh deployment with no database rows
  behaves exactly as before, seeded from the environment.

*Unfavourable, and accepted:*

- Two sources of configuration now exist (environment seed + database override).
  The resolution order is fixed and documented to keep this unambiguous.
- Applying overrides mutates the in-memory settings view at run start; acceptable
  for a single-operator, low-concurrency system.
- Additional schema and UI surface, against the §11 time-box. Mitigated by
  reusing the existing template and endpoint patterns.

## Control

Consistent with the §11 discipline: the configuration UI is built to the minimum
that supports operator self-service (edit operational settings; CRUD + schedule +
run-now for profiles). Anything beyond that is deferred. `.env.example` is retained
as the documented seed and bootstrap.
