# Phase 1 Contract: CLI Surface

**Date**: 13 August 2026 | **Plan**: [plan.md](../plan.md)

This is the published interface. The command surface, the exit codes, and the
JSON projections are what scripts depend on; changing any of them is a breaking
change and needs the same scrutiny as a schema change.

The per-command specification — every option, its service, and its error paths —
is [Docs/CLI-Support.md](../../../Docs/CLI-Support.md) §3.2 and is not duplicated
here. This file fixes the three things that must not drift.

---

## 1. Command surface

```text
job-discovery                     (= python -m app)
│
│  global: --log-level  --quiet/-q  --traceback  --version
│
├── collect                       stage 1                    [existing, frozen]
├── normalise [--run-id N]        stage 2                    [existing, frozen]
├── score                         stage 3 stub → exit 1      [existing, frozen]
├── publish                       stage 4 stub → exit 1      [existing, frozen]
├── run-all                       every stage in order       [existing, frozen]
├── serve                         scheduler, foreground      [existing, COMPOSE CONTRACT]
├── web  [--host --port --reload] triage interface           [existing, COMPOSE CONTRACT]
├── status [--limit]              recent runs                [existing, frozen]
├── config                        env-resolved config        [existing, frozen]
│
├── postings    list · get · set-status
├── employers   blacklisted · blacklist · unblacklist · resweep
├── profiles    list · create · update · enable · disable · delete · run
├── settings    show · set
├── runs        list · health
└── reports     employers · sources
```

**Frozen** means the name, options, defaults, output text, and exit code are
byte-identical before and after the restructure (FR-001). **Compose contract**
additionally means `docker-compose.yml` invokes it directly, so a change breaks
deployment silently rather than loudly.

`--output/-o table|json` is available on every command in the lower block.

### Two names that deliberately do not collide

- **`status` ≠ `postings status`.** `status` means "recent runs" and keeps that
  meaning. Triage state is set with `postings set-status`.
- **`config` ≠ `settings show`.** `config` reads the environment only and needs
  no database — what an operator wants during an outage. `settings show` reads
  database-resolved effective values. Neither is an alias for the other, and both
  say so in their help.

---

## 2. Exit-code contract

| Code | Meaning | Emitted for |
|---|---|---|
| `0` | Success | Normal return. **An empty result set is success.** |
| `1` | Business / application failure | `ProfileError` from create/update, `ValidationError` from a settings write, the `score`/`publish` stubs |
| `2` | Invalid CLI usage | Bad option, bad `Choice`, missing argument. Click's own default — never re-implemented |
| `3` | Not found | `EmployerNotFoundError`; `get_posting`/`set_status` returning `None`; `ProfileError` from `set_enabled`/`delete`, where "not found" is its only cause |
| `4` | Infrastructure failure | `OperationalError` / `DBAPIError` — database unreachable, schema not migrated |
| `70` | Unexpected internal error | Anything else. One-line message; traceback only under `--traceback`. `EX_SOFTWARE` from `sysexits.h` |

**The `1` vs `3` split is the contract's whole point.** A script must be able to
tell "that id does not exist" from "the database is down" without parsing a
message. Adding a seventh code requires a constitution amendment.

---

## 3. JSON projections

JSON is built from **explicit dictionaries**, never from serialised ORM rows, so
a column rename cannot silently alter the published shape. Field names below are
the contract; the service attributes they are projected from are noted where the
two differ.

### `postings list`

```json
{
  "postings": [
    {
      "id": 42,
      "status": "new",
      "score": 78,
      "employer": "PwC",
      "title": "Data Engineer",
      "country": "eg",
      "remote": false,
      "published": true,
      "sources": ["indeed", "linkedin"]
    }
  ],
  "page": { "number": 1, "per_page": 50, "pages": 4, "total": 187,
            "first": 1, "last": 50 }
}
```

`page` is projected from `queries.Page` — `total` and `number` are fields;
`pages`, `first`, and `last` are its properties. `country` comes from
`Posting.country_code`; `remote` from `is_remote`.

### `postings get`

The single-posting object above, plus the full field block and per-board
provenance expanded one entry per board rather than a bare list.

### `employers blacklisted`

```json
{ "employers": [ { "id": 3, "name": "PwC", "postings": 12 } ] }
```

Projected from `queries.blacklisted_employers`, which returns
`list[tuple[Employer, int]]`.

### `profiles list`

```json
{
  "profiles": [
    { "id": 4, "name": "Cairo DE", "enabled": true, "term": "data engineer",
      "location": null, "country": "egypt", "remote": false,
      "sites": ["indeed", "linkedin"], "experience": null,
      "schedule": "06:00" }
  ]
}
```

`schedule` is a formatted `HH:MM` projection of `schedule_hour` and
`schedule_minute` — two columns, one field, deliberately.

### `settings show`

```json
{
  "settings": [
    { "key": "results_per_search", "value": 100, "source": "database", "editable": true },
    { "key": "proxies", "value": "***", "source": "environment", "editable": true },
    { "key": "timezone", "value": "Africa/Cairo", "source": "environment", "editable": false }
  ]
}
```

`source` is one of `database` · `environment` · `default`, matching the ADR-0005
resolution order. **`proxies` and `database_url` are masked unconditionally in
this payload** — there is no flag that unmasks them (FR-021).

### `runs list`

```json
{
  "runs": [
    { "id": 91, "started_at": "2026-08-13T06:00:00+00:00", "finished_at": "2026-08-13T06:04:11+00:00",
      "status": "success", "profile": "Cairo DE", "collected": 148,
      "deduplicated": 96, "counts_by_site": { "indeed": 91, "linkedin": 57 },
      "error": null }
  ]
}
```

Timestamps are ISO-8601 with an explicit offset, everywhere, in every command.

### `runs health`

```json
{
  "sites": ["indeed", "linkedin"],
  "series": {
    "indeed":   [ { "started_at": "2026-08-12T06:00:00+00:00", "count": 88 },
                  { "started_at": "2026-08-13T06:00:00+00:00", "count": 91 } ]
  }
}
```

`queries.source_health` returns `(datetime, int)` tuples in run order, oldest
first. The projection names both members rather than emitting positional pairs —
**this is the series a monitor alerts on**, and positional data is the wrong
thing to publish.

### `reports employers`

```json
{
  "employers": [
    { "employer": "PwC", "postings": 12, "titles": 3,
      "first_seen": "2026-06-01T08:12:00+00:00",
      "latest_seen": "2026-08-11T09:02:00+00:00",
      "days_quiet": 2, "by_status": { "new": 7, "rejected": 5 } }
  ],
  "caveat": "…"
}
```

### `reports sources`

```json
{
  "sites": ["indeed", "linkedin"],
  "per_site": { "indeed": 140, "linkedin": 96 },
  "combinations": [ { "sites": ["indeed"], "count": 84 },
                    { "sites": ["indeed", "linkedin"], "count": 56 } ],
  "first_by": { "indeed": 39, "linkedin": 12 },
  "ties": 5, "contested": 56, "total": 187,
  "caveat": "…"
}
```

`SourceOverlap.combinations` is `list[tuple[tuple[str, ...], int]]`; the
projection names the members for the same reason as `series` above.

### The `caveat` field is mandatory

**Both report payloads carry the ADR-0008 §1 sampling-bias caveat**, and both
table outputs carry it as a footer line. That caveat is the condition on which
each report was admitted. `tests/test_web_reports.py` already asserts it for the
templates; the CLI tests assert it for both formats — a caveat nothing tests is a
caveat that disappears in the next layout change.

---

## 4. Stream contract

| Stream | Carries |
|---|---|
| **stdout** | Results only — tables and JSON |
| **stderr** | Everything else — application logs, progress, error messages, confirmation prompts |

`--output json` must produce stdout that parses cleanly **while services log at
INFO**. This is asserted, not assumed: Click 8.4.2's `CliRunner` separates the
two streams by default, which is what makes the assertion possible.

`--quiet` raises the log threshold to `WARNING`. It does not redirect a stream,
and it does not suppress results.

---

## 5. Confirmation contract

Four commands mutate destructively or system-wide:

| Command | Why it confirms |
|---|---|
| `profiles delete` | Hard delete |
| `employers blacklist` | Mass rejection and un-publication in one transaction |
| `postings set-status` | When more than one id is given, or the target status is `rejected` |
| `settings set` | Changes behaviour for the scheduler and every other process — echoes before → after rather than prompting |

Rules for the first three:

1. On an interactive terminal, prompt — and **state the number of records
   affected**, not merely "are you sure?".
2. With `--yes/-y`, proceed without prompting.
3. With no terminal attached and no `--yes`, **fail loudly** rather than block on
   a prompt nobody can answer.

Rule 3 is the one that matters in CI, and it is the one most likely to be
omitted.

---

## 6. What is deliberately not in the contract

- **No `--database-url`, and no per-command database selection.** The database is
  process-wide, resolved from the environment before the engine is built (FR-019,
  FR-020).
- **No `--show-secrets`.** Anyone entitled to the raw values can read `.env`.
- **No `country=remote` sentinel.** The web overloads one `country` selector to
  carry the remote axis because an HTML form had a single dropdown to spend.
  `queries.list_postings` exposes `remote` as a real tri-state parameter, so the
  CLI takes `--remote/--on-site` and leaves the sentinel in the web form where it
  belongs.
- **No `--reason` on bulk transitions.** `triage.set_status_bulk` takes no
  reason, so `--reason` is accepted for the single-id form only. The asymmetry is
  pre-existing and is surfaced in help text rather than papered over.
