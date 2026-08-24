# Notices

## Legal and usage notice

**This is not legal advice.** It is a plain description of what the software
does, so you can decide for yourself what your obligations are. If you need a
legal answer, ask a lawyer.

### The pipeline scrapes job boards

Stage 1 collects postings from **Indeed** and **LinkedIn** through
[JobSpy](https://github.com/cullenwatson/JobSpy). It does this by issuing
requests to those sites and parsing the responses — it is not using an official
API, and no board has authorised or endorsed this project.

**You are responsible for your own use of it.** In particular:

- **Terms of service.** Job boards set their own terms governing automated
  access. Review the terms of any board you point this at, and use it in a way
  that complies with them.
- **Rate limiting.** `REQUEST_DELAY_SECONDS` defaults to 10 seconds, deliberately
  conservative (design §9.3). **Do not lower it to make collection faster.**
  Raising the delay is the first remedy for being restricted; proxies are the
  last. Aggressive collection gets your IP blocked and puts avoidable load on a
  service other people depend on.
- **Volume.** `RESULTS_PER_SEARCH` and the number of configured searches
  multiply into request count. The default schedule runs **once daily**. Keep it
  proportionate to one person's job search — that is the workload this was
  designed for and tested at.
- **Jurisdiction.** The legality of scraping publicly accessible pages varies
  by country and has been litigated inconsistently. Where you run this matters.

The maintainers provide this software as-is under the [Apache License
2.0](LICENSE), which disclaims warranty and liability. Nothing here is a
representation that any particular use is lawful.

### The data it collects is personal data

Two categories, both under **your** control as the operator:

1. **Your CV** (`app/data/cv.txt`) — mounted read-only into the containers and
   used to build the stage 3 scoring prompt. It is sent to Ollama, which runs
   on your machine.
2. **Collected job postings** — employer names, titles, locations, descriptions
   and URLs, stored in your local PostgreSQL. Postings routinely include
   recruiter names and contact details, which are personal data about *other*
   people.

Because this runs entirely on your hardware, **you are the data controller**.
There is no shared service, no maintainer-operated backend, and no one else
holding a copy. Practically:

- If you are in a jurisdiction with data-protection law (GDPR, UK GDPR, and
  similar), holding scraped personal data about identifiable individuals may
  carry obligations — retention limits, and rights of access and erasure among
  them. A purely personal job search may fall under a household exemption; using
  it for recruitment, research, or anything commercial very likely does not.
- **Do not republish the collected data.** Aggregating postings for your own
  reading is a different act from redistributing them.
- Delete what you no longer need. The database is yours; nothing prunes it for
  you.
- Back up the `pgdata` volume with the same care as any other personal data,
  and remember `app/data/cv.txt` is excluded from git for a reason.

### The "no data leaves the machine" property

The project's central constraint is that scoring happens locally via Ollama,
so CV text and posting descriptions are never sent to a third-party model
provider. **This property is configuration-dependent.** Pointing `OLLAMA_HOST`
at a remote endpoint breaks it. CI flags a non-local `OLLAMA_HOST` for exactly
this reason — see [SECURITY.md](SECURITY.md).

---

## Third-party software

This product includes software developed by third parties. The full dependency
graph and its exact versions are pinned in [`app/uv.lock`](app/uv.lock).

Principal dependencies and their licences:

| Component | Licence | Role |
|---|---|---|
| [python-jobspy](https://github.com/cullenwatson/JobSpy) | MIT | Job board collection (stage 1) |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Triage web interface |
| [SQLAlchemy](https://www.sqlalchemy.org/) | MIT | ORM and database access |
| [Alembic](https://alembic.sqlalchemy.org/) | MIT | Schema migrations |
| [pydantic](https://docs.pydantic.dev/) / pydantic-settings | MIT | Typed configuration and validation |
| [Typer](https://typer.tiangolo.com/) | MIT | CLI |
| [APScheduler](https://github.com/agronholm/apscheduler) | MIT | Daily scheduling |
| [ollama-python](https://github.com/ollama/ollama-python) | MIT | Local model client (stage 3) |
| [pgvector-python](https://github.com/pgvector/pgvector-python) | MIT | Vector column support |
| [Uvicorn](https://www.uvicorn.org/) | BSD-3-Clause | ASGI server |
| [Jinja2](https://jinja.palletsprojects.com/) | BSD-3-Clause | Templates |
| **[psycopg](https://www.psycopg.org/) 3** | **LGPL-3.0-only** | PostgreSQL driver |

### A note on psycopg and the LGPL

psycopg 3 is the one copyleft dependency. It is used as an **unmodified,
separately-installed library** imported at runtime, which is the case the LGPL
is written to permit — it imposes no licensing requirement on this project's own
Apache-2.0 code.

It does carry one obligation worth knowing: **the container image built from
`app/Dockerfile` bundles `psycopg[binary]`**. If you distribute that image
rather than just running it yourself, you are distributing LGPL-licensed
binaries, and the LGPL's notice and relinking provisions apply to that
distribution. Running it locally — the intended use — involves no distribution
and no obligation.

The project does not vendor, fork or modify any dependency.

---

## Attribution

Copyright 2026 Mohammed Kenawy.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
