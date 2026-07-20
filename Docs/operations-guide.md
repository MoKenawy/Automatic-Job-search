# Operations Guide
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 21 July 2026 |
| **Audience** | Operator |
| **Related** | [Deployment Guide](deployment-guide.md), [System Architecture](design/system-architecture.md) |

---

## 1. Purpose

This guide covers running the system day to day once it is deployed: the daily
rhythm, how to read run health, how to intervene when a source degrades, and how
to look after the data. It assumes the system is already stood up per the
[Deployment Guide](deployment-guide.md).

The operating principle throughout is the one from the design record (§2): the
scarce resource is attention, not postings. The system exists to save you effort,
and any procedure here that takes more than a few minutes a day is a sign
something is wrong.

---

## 2. Daily rhythm

The `scheduler` service runs the full pipeline once daily at the configured time
(06:00 by default). In normal operation there is nothing to do but review:

1. Open the interface at `http://localhost:8000`.
2. Read the overview: how many postings, how many published, and the source-health
   sparklines.
3. Work the **Postings** list top-down (highest score first). For each worth
   pursuing, open it, read the description beside the assessment, and set its
   status to **Shortlist**; set clearly irrelevant ones to **Rejected**.
4. Shortlisted roles you apply to become **Applied**.

Target effort is under five minutes (SRS NFR-2). Rejected postings never
resurface, so rejecting aggressively is safe and keeps the list clean.

---

## 3. Triggering a run manually

The scheduler runs daily, but you can run any stage on demand.

```powershell
# Full pipeline
docker compose exec scheduler python -m app run-all

# Individual stages (each idempotent, re-runnable)
docker compose exec scheduler python -m app collect
docker compose exec scheduler python -m app normalise
```

To run against the database from the host instead of inside a container (requires
`uv` and the database port published):

```powershell
cd app
uv run python -m app run-all
```

Check recent runs from the command line:

```powershell
docker compose exec scheduler python -m app status
```

---

## 4. Weekly review — the one procedure that matters

**This is the most important recurring task.** The dominant failure mode is not a
crash. It is a run that reports success while a source quietly returns fewer
postings as it begins restricting access (design §7.4). The aggregate numbers
look fine; only the per-source trend reveals it.

Once a week, open the **Runs** view (`/runs`) and look at the per-source
sparklines:

| What you see | What it means | Action |
|---|---|---|
| Bars roughly level | Healthy | None |
| One source trending down over several runs | That source is degrading | §5 — increase delay |
| A source at zero (red bar) for recent runs | That source is blocked or broken | §5 — investigate |
| A run marked `failed` | The pipeline errored | Read the error in the run row |

A single low run is noise. A **trend** across several runs is signal. The whole
reason counts are persisted per source is to make this judgement possible — do
not skip it.

---

## 5. Responding to source degradation

When a source degrades, escalate in this order (design §9.3) — cheapest first:

1. **Increase the request delay.** Edit `REQUEST_DELAY_SECONDS` in `.env` (e.g.
   from 10 to 20) and restart the scheduler:

   ```powershell
   docker compose up -d scheduler
   ```

2. **Reduce volume.** Lower `RESULTS_PER_SEARCH`, or narrow `SEARCHES`.

3. **Wait.** IP-level restrictions are typically temporary. Because no
   credentials are supplied to any board, there is no account to suspend — the
   exposure is a temporary IP block, not a lasting loss (design §4).

4. **Proxy provision** is the last resort, and the only measure that carries a
   cost. It is warranted only if a degraded source is judged worth retaining.
   Configure `PROXIES` in `.env` as a JSON array.

Because the design is multi-source, one source degrading does not stop the
pipeline — the others continue, and the run still succeeds. This is by design,
which is also why the degradation is easy to miss without the weekly review.

---

## 6. Tuning the scorer *(once scoring is enabled)*

The publication threshold starts deliberately permissive at 60 (design D7), so
that during the first week you see roughly what the model rates borderline. Use
the detail view to compare the model's score and rationale against your own
judgement:

- If the model publishes roles you would reject → raise `PUBLISH_THRESHOLD`.
- If it rejects roles you would pursue → lower it, or revisit the prompt.

Adjust in `.env` and restart the scheduler. Scoring can be re-run over the whole
stored corpus after a change without re-collecting (design §7.2):

```powershell
docker compose exec scheduler python -m app score
docker compose exec scheduler python -m app publish
```

Before trusting the scorer at all, check a sample of its output by hand. A scorer
that quietly disagrees with your judgement is worse than none, because its output
will be trusted (design §12 item 9).

---

## 7. Health and logs

```powershell
# Service status
docker compose ps -a

# Liveness + database reachability
Invoke-WebRequest http://localhost:8000/healthz -UseBasicParsing

# Logs
docker compose logs -f scheduler     # follow the scheduler
docker compose logs web              # web server
docker compose logs migrate          # migration output (from last startup)
```

Expected steady state: `db` healthy, `web` healthy, `scheduler` up, `migrate`
exited 0. The scheduler log shows the next scheduled run when it starts.

---

## 8. Data care

### 8.1 What is retained

Everything, deliberately. Raw collector output is kept for reprocessing and
diagnosis; deduplicated postings are kept indefinitely; rejected postings are
kept so they never resurface (design D9). This is a personal single-machine
system, and the data is small — there is no retention policy to enforce.

### 8.2 Backup

The entire state lives in the `pgdata` Docker volume. To back it up:

```powershell
docker compose exec -T postgres pg_dump -U jobs jobs > backup_$(Get-Date -Format yyyyMMdd).sql
```

To restore into a fresh database:

```powershell
docker compose exec -T postgres psql -U jobs -d jobs < backup_20260721.sql
```

### 8.3 Inspecting the database directly

```powershell
docker compose exec postgres psql -U jobs -d jobs

# Useful queries
SELECT status, count(*) FROM postings GROUP BY status;
SELECT id, started_at, status, collected_count, deduplicated_count, counts_by_site FROM runs ORDER BY started_at DESC LIMIT 10;
```

---

## 9. The standing risk

The design record names the principal risk plainly (§11): this build is engaging
and adjacent to a specialisation interest, and therefore easily mistaken for
progress. Applications are not submitted while a model is being tuned.

The operating discipline that follows: **the pipeline earns its place only by
being used.** If a week passes where you tuned the system but sent no
applications, the system is not serving its purpose — triage manually and apply,
and treat further build work as deferred. The interface exists to make applying
easier, not to become the activity.

---

## 10. Quick reference

| Task | Command |
|---|---|
| Open interface | `http://localhost:8000` |
| Run full pipeline now | `docker compose exec scheduler python -m app run-all` |
| Recent run counts | `docker compose exec scheduler python -m app status` |
| Effective config | `docker compose exec scheduler python -m app config` |
| Service status | `docker compose ps -a` |
| Follow scheduler logs | `docker compose logs -f scheduler` |
| Restart after config change | `docker compose up -d scheduler` |
| Back up data | `docker compose exec -T postgres pg_dump -U jobs jobs > backup.sql` |

*End of document.*
