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

## 6a. Self-service configuration (feature 001, ADR-0005)

The interface now manages what used to require editing `.env` and restarting.

**Blacklist** (`/blacklist`). Blacklisting an employer withholds every posting
from them — existing and future — from your views; the postings are retained and
never published. Do this from the employer's row on a posting detail page, or
manage the list on the Blacklist page. Removing a blacklist brings their
postings back **with whatever triage status they already had**: nothing was
overwritten, so nothing needs reinstating (ADR-0015). Expect the back catalogue
to reappear in the queue on a lift.

**Filtered out** (`/postings?verdict=rejected`). The postings the filter turned
away, under the criteria in force now, with the criterion that turned each one
away. Two criteria apply (ADR-0016):

- **Title** — the include/exclude patterns at `/settings`, applied to the job
  title only, and optionally each profile's own on `/profiles`. Both levels are
  empty by default, and an empty pattern means the criterion is off.
- **Experience** — the level recorded on a search profile, compared against the
  board's declared seniority (or, where no board declared one, a cautious
  reading of the title). A request admits everything at or below it. A posting
  whose level is unknown is always admitted.

A rejected posting is **withheld, not deleted**, and only while it is still
untriaged — anything you have shortlisted or applied to stays in the queue, so a
criteria change never withdraws your own judgement. To bring a withheld posting
back: loosen the criterion, then re-apply with `filter --all`. Its triage status
is untouched.

Expect filtering to begin on the first run after installation if a profile
already records an experience level. Measure it first:

```powershell
docker compose exec scheduler python -m app filter --all --dry-run
```

That reports what would change and writes nothing.

**Filter rules per profile** (`/profiles`, *Filter rules* under each profile).
Each profile can carry its own title patterns and experience level. Four
things are worth knowing before relying on them (ADR-0018):

- **They add to the global rules, never replace them.** A pattern at
  `/settings` binds every posting whatever profile found it, and a profile
  cannot loosen it.
- **Exclude always beats include**, within a profile and across the two levels.
  A profile that asks for `senior` does not get it past a global exclude of
  `senior`.
- **A blank *Experience* box means that profile never hides anything on
  seniority grounds.** It is not "no preference, defer to the others": for
  every posting that profile found, it votes to admit. When a posting was
  found by several profiles, it is kept if *any* of them would keep it, so one
  profile with the box empty switches seniority filtering off for everything
  it shares with profiles that did fill it in. This is deliberate — the
  alternative lets a profile you are not thinking about conceal a posting
  another one wanted — but it surprises people. **Fill the box in on every
  profile where you want seniority filtering.**
- **A profile's exclude can be defeated by another profile** that found the
  same posting and excludes nothing, for the same reason. A rule that must be
  absolute belongs in the global settings. On a typical corpus most postings
  (about nine in ten) are found by one profile only and are governed fully.

A change to any of these reaches postings already collected once you run
`filter --all`; nothing is re-collected, and a posting a rule withheld comes
back, triage status intact, when the rule is loosened and the filter re-applied.

If most of your LinkedIn postings land under *filtered out*, that is the
seniority criterion working as specified, not LinkedIn being blocked:
LinkedIn labels many ordinary roles `mid-senior level`. ADR-0017 accepted this
behaviour as built: the board's label decides, and the title is read only where
the board is silent. The withheld postings stay reachable at *filtered out*,
each with its grounds. If you think the label is hiding too much, say so: the
record names the measurement that would reopen the question.

**Setting up a new profile: search term and experience** (ADR-0020). The two
boxes do different jobs, and mixing them up costs postings you never see.

- **The search term is what the boards receive.** It goes to each board as a
  plain keyword search, exactly as typed. JobSpy, the library behind collection,
  has no experience or seniority parameter for any board, so the term is the
  only control you have over *what is collected*. Each board returns at most
  *results per search* rows (`/settings`) for each search, so the term also
  decides which rows fill that cap.
- **Name the role only** — `data engineer`, not `junior data engineer`. Boards
  match keywords, not seniority, so adding *junior* drops every plainly titled
  entry role ("Data Engineer") before it is collected. It also pulls in senior
  postings whose description merely mentions juniors. A posting that was never
  collected cannot be brought back by loosening a rule.
- **Put the seniority in *Experience*.** It is applied *after* collection, to
  everything the profile found, and can be changed and re-applied to history at
  any time. Words it understands, lowest to highest:

  | Write | Level | Hides |
  |---|---|---|
  | `intern`, `internship`, `trainee` | internship | everything above internship |
  | `entry level`, `junior`, `graduate`, `fresher` | entry | mid-senior and above (an entry request also admits *associate*) |
  | `associate` | associate | mid-senior and above |
  | `mid`, `senior`, `lead`, `staff`, `principal` | mid-senior | director and executive |
  | `director`, `head` | director | executive |
  | `executive`, `chief`, `vp` | executive | nothing |

  A blank box means no seniority filtering for that profile. Text it cannot
  read (or a range such as `junior to senior`) is ignored, and the filter run
  logs it as unreadable.
- **The boards are judged differently.** LinkedIn states a seniority on each
  posting ("Seniority level"), and that label decides. Indeed states none, so an
  Indeed posting is hidden only when its *title* carries a seniority word
  ("Senior", "Lead", "Principal" …); a plainly titled Indeed posting is always
  kept. (Naukri publishes an experience range, but it is not one of the boards
  collected.)
- **Want more entry-level results?** Add a **second** profile with a
  seniority-qualified term (`junior data engineer`, `graduate data engineer`)
  *alongside* the plain one, with the same Experience. It surfaces roles the plain
  search's cap may have crowded out. Never *replace* the plain term with it. Each
  extra profile is another set of requests to the boards, so add them sparingly.
- After changing a profile's Experience, measure with
  `filter --all --dry-run`, then apply with `filter --all`.

**Settings** (`/settings`). Operational values — results per search, request
delay, publish threshold, scoring model, LinkedIn description fetch, title
filters, proxies — are edited here and take effect on the next run with no
restart. Invalid values are rejected and the prior value stands, which now
includes a title pattern that is not a valid expression. Restart-only settings
(timezone, bind host/port) are shown read-only; the database URL is not shown.

One coupling is worth knowing: **LinkedIn declares a posting's seniority only
when description fetching is on**, so turning `linkedin_fetch_description` off
also turns off most of the experience filter's input. It fails open — nothing is
wrongly withheld — but it fails quietly, so nothing will tell you it happened.

**Schedules** (`/profiles`). Each search profile is a saved survey — role,
location, sites, remote, experience — with its own run time and an enabled flag.
Enabled profiles run automatically at their time; "run now" runs one immediately.
Disabling a profile retains it for later. This replaces the single global 06:00
job: the scheduler now runs one job per enabled profile.

**Quick triage** (`/postings`). Change a posting's status inline from its row, or
select several and apply one status in bulk — no need to open each posting.

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
| Re-apply the filter after a criteria change | `docker compose exec scheduler python -m app filter --all` |
| See what the filter would change, writing nothing | `docker compose exec scheduler python -m app filter --all --dry-run` |
| Effective config | `docker compose exec scheduler python -m app config` |
| Service status | `docker compose ps -a` |
| Follow scheduler logs | `docker compose logs -f scheduler` |
| Restart after config change | `docker compose up -d scheduler` |
| Back up data | `docker compose exec -T postgres pg_dump -U jobs jobs > backup.sql` |

*End of document.*
