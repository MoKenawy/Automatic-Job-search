# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report privately through **[GitHub Security Advisories](https://github.com/MoKenawy/Automatic-Job-search/security/advisories/new)**
("Security" → "Report a vulnerability"). That gives us a private thread, a
tracking record, and a CVE if one is warranted.

If you cannot use GitHub Advisories, email **mokenawy.business@gmail.com** with
`SECURITY` in the subject.

Please include: what you found, how to reproduce it, what an attacker gains,
and the version or commit you tested.

### What to expect

| | |
|---|---|
| Acknowledgement | Within 5 working days |
| Initial assessment | Within 10 working days |
| Fix or mitigation plan | Communicated in the advisory thread |
| Credit | Offered in the advisory unless you prefer otherwise |

This is a personal open-source project maintained in spare time. There is no
paid security team and no formal SLA — the timelines above are honest
intentions, not contractual commitments. If something is being actively
exploited, say so prominently and it will be prioritised.

## Supported versions

The project is pre-1.0 and stages 3–4 are unbuilt. **Only `main` is supported.**
Fixes land on `main`; there are no maintained release branches and no backports.
There is no published release artifact — deployment is from a git checkout.

| Version | Supported |
|---|---|
| `main` | Yes |
| Tagged releases | None yet |
| Feature branches | No |

---

## Known security surface

This section is deliberately specific. Most of what follows is **intended
behaviour for a single-operator local tool**, not a defect — but each item is a
real risk if the system is deployed outside the assumptions it was built for.
Please read it before reporting; a report that the web UI has no login is
already answered here.

### The web interface has no authentication, and binds to all interfaces

`WEB_HOST` defaults to `0.0.0.0` ([`config.py:73`](app/src/app/config.py)) and
Compose publishes port 8000. There is **no login, no session, no CSRF token,
and no authorisation check** anywhere in `app/src/app/web/`.

The design assumes a machine only the operator can reach. On a shared network,
a VPS, or any host with an open firewall, **anyone who can reach port 8000 can
read every collected posting and change triage state**.

If the host is not fully trusted:

- Set `WEB_HOST=127.0.0.1` so the interface is reachable only from the machine
  itself, and reach it over an SSH tunnel.
- Or put it behind a reverse proxy that terminates TLS and enforces
  authentication.
- Do not publish port 8000 to a public interface. Remove the `ports:` mapping
  for the `web` service if you only need local access.

### Default database credentials are `jobs` / `jobs`

`POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` all default to `jobs`
(`.env.example`, `docker-compose.yml`), and Compose publishes **5432 on the
host**. These are documented development defaults, published deliberately so
the quick start works.

Change them before running on any machine that is not your own workstation, and
consider removing the published port mapping — the application containers reach
Postgres over the Compose network and do not need it exposed.

### The system stores personal data locally

- `app/data/cv.txt` — the operator's actual CV, mounted read-only into the
  containers for stage 3 scoring.
- The database — collected job postings, including employer names and full
  descriptions scraped from job boards.

Neither is encrypted at rest beyond whatever the host filesystem provides. Both
are excluded from git by `.gitignore`. **Back up the `pgdata` volume with the
same care you would give any other personal data**, and see [NOTICE.md](NOTICE.md)
for the data-protection responsibilities that come with holding it.

### Scraping and third-party endpoints

The pipeline makes outbound requests to job boards via JobSpy, and to Ollama for
scoring. `PROXIES` may carry credentialed proxy URLs; the CLI's `config`
command masks `database_url` and `proxies` for this reason. If you add a command
that prints effective configuration, **it must mask both**.

`OLLAMA_HOST` is expected to be `localhost` or `host.docker.internal`. Pointing
it at a remote endpoint sends CV text and scraped descriptions off the machine,
which defeats the project's core "no data leaves the machine" property. CI
flags a non-local `OLLAMA_HOST` for this reason.

### Not in scope

- The absence of authentication on the web UI, as described above.
- Default development credentials, as described above.
- Denial of service against your own local instance.
- Vulnerabilities in job boards themselves, or in JobSpy — report those upstream.
- Getting rate-limited or blocked by a job board. See [NOTICE.md](NOTICE.md).

---

## Secret-scanning practice

Every pull request is scanned with
[TruffleHog](https://github.com/trufflesecurity/trufflehog); pushes to `main`
scan the **entire history**, not just the diff, because a secret committed and
later "removed" is still in the history and still compromised.

Configuration lives in [`.trufflehog/`](.trufflehog/):

- `config.yaml` — custom detectors for this project's shapes (`DATABASE_URL`
  DSNs with non-default credentials, `PROXIES` entries with embedded auth,
  non-local `OLLAMA_HOST`), plus allowlists for the documented local defaults so
  they do not drown the signal.
- `includes.txt` / `excludes.txt` — path filters, one **regex** per line.
  `app/migrations/` is deliberately kept in scope: a data migration is one of
  the few places a real credential plausibly gets pasted.

Contributors can run the identical scan locally — see
[CONTRIBUTING.md](CONTRIBUTING.md#running-the-secret-scan-locally).
