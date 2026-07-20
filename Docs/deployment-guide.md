# Deployment Guide
## Automated Job Discovery Pipeline

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 21 July 2026 |
| **Audience** | Operator |
| **Related** | [System Architecture](design/system-architecture.md), [Operations Guide](operations-guide.md) |

---

## 1. Purpose

This guide stands the system up on a single machine, from nothing to a running
pipeline with a reachable interface. It assumes the reader can run a terminal but
assumes no prior knowledge of the project.

For working on the code, see the [Development Guide](development-guide.md). For
running the system day to day, see the [Operations Guide](operations-guide.md).

---

## 2. Prerequisites

| Requirement | Purpose | Notes |
|---|---|---|
| **Docker Desktop** | PostgreSQL and the application containers | Requires the Virtual Machine Platform feature and virtualization enabled in firmware |
| **Ollama** | Local scoring model (stages 3–4) | Runs on the host, not in a container, to use the GPU directly |
| **uv** *(host runs only)* | Running the CLI outside Docker | Optional; only needed for host-side operation |

The system targets Windows 11 with Docker Desktop. Commands below are given for
PowerShell.

### 2.1 Verify Docker

```powershell
docker --version
docker compose version
docker info --format '{{.ServerVersion}} / {{.OSType}}'
```

If `docker info` returns an error, the daemon is not ready — start Docker Desktop
and wait for it to report running. If Docker is not installed at all, install
Docker Desktop; it will prompt to enable the Virtual Machine Platform feature and
reboot.

---

## 3. Configuration

All configuration is supplied through a `.env` file. Copy the template and edit:

```powershell
cd app
Copy-Item .env.example .env
```

The settings that matter at deployment time:

| Variable | Meaning | Default |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database credentials | `jobs` / `jobs` / `jobs` |
| `DATABASE_URL` | Connection string for host-side runs | points at `localhost:5432` |
| `SEARCHES` | JSON array of search specifications | data-engineer, Cairo + remote |
| `RESULTS_PER_SEARCH` | Postings requested per board per search | `50` |
| `REQUEST_DELAY_SECONDS` | Inter-request delay (collection etiquette) | `10` |
| `SCORING_MODEL` | Ollama model tag | `qwen2.5:7b-instruct` |
| `CV_PATH` | CV used to build the scoring prompt | `data/cv.txt` |
| `PUBLISH_THRESHOLD` | Minimum score to publish | `60` |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` / `TIMEZONE` | Daily run time | `06:00` `Africa/Cairo` |

Inside Compose, `DATABASE_URL` and `OLLAMA_HOST` are overridden automatically so
the containers reach `postgres` and `host.docker.internal`; the `.env` values for
those two are used only for host-side runs.

> **Note.** `TIMEZONE` determines when the daily run fires. The default is
> `Africa/Cairo`; set it to your own zone.

---

## 4. First deployment

From the `app/` directory:

```powershell
# 1. Pull the database image (retry if the registry connection drops)
docker compose pull postgres

# 2. Build the application image
docker compose build

# 3. Bring the whole stack up
docker compose up -d
```

Step 3 starts four services in order: `postgres` becomes healthy, `migrate`
applies the schema and exits, then `web` and `scheduler` start.

### 4.1 Verify

```powershell
docker compose ps -a
```

Expected:

| Service | Expected status |
|---|---|
| `job-discovery-db` | `Up (healthy)` |
| `job-discovery-migrate` | `Exited (0)` |
| `job-discovery-web` | `Up (healthy)` |
| `job-discovery-scheduler` | `Up` |

`migrate` **exiting 0 is correct** — it is a one-shot job, not a failure. Then
open the interface:

```
http://localhost:8000
```

A health check without a browser:

```powershell
Invoke-WebRequest http://localhost:8000/healthz -UseBasicParsing
```

---

## 5. Enabling scoring (stages 3–4)

Collection and deduplication work without any further setup. Scoring requires
two things (currently a **planned** stage):

1. **A CV** in plain text at `app/data/cv.txt`. The `data/` directory is mounted
   read-only into the containers.
2. **A model pulled into Ollama** on the host:

   ```powershell
   ollama pull qwen2.5:7b-instruct
   ```

Confirm the containers can reach Ollama:

```powershell
docker compose exec web python -c "import urllib.request as u; print(u.urlopen('http://host.docker.internal:11434/api/tags').status)"
```

A `200` confirms reachability.

---

## 6. Common deployment problems

| Symptom | Cause | Remedy |
|---|---|---|
| `docker info` errors | Daemon not started | Start Docker Desktop; wait for running |
| `pull` fails mid-blob with `EOF` | Transient registry/network drop | Re-run `docker compose pull`; completed layers are cached |
| Build fails resolving `docker/dockerfile:1` | DNS/registry hiccup | Retry the build |
| `web` unhealthy, logs show DB connection refused | `migrate` did not complete | Check `docker compose logs migrate`; ensure `postgres` is healthy |
| Interface reachable but empty | No run has executed yet | Trigger one — see Operations Guide §3 |
| Scoring errors reaching Ollama | Ollama not running, or model not pulled | Start Ollama; `ollama pull <model>` |

---

## 7. Updating a running deployment

After pulling new code:

```powershell
docker compose build
docker compose up -d          # recreates changed services
```

If the update includes a migration, `migrate` runs it automatically on the way
up, before `web` and `scheduler` restart. To apply migrations without a full
redeploy:

```powershell
docker compose run --rm migrate
```

---

## 8. Teardown

```powershell
# Stop and remove containers, keep the database volume
docker compose down

# Also remove the database volume (destroys all collected data)
docker compose down -v
```

`docker compose down -v` is destructive: it deletes the `pgdata` volume and with
it every collected posting, run record and triage decision. Use it only when you
intend to start from an empty database.

*End of document.*
