"""Command-line entry point.

Each pipeline stage is a subcommand, so any stage can be re-run independently
against the staging database without repeating the ones before it (design §7.1).
"""

import logging

import typer

from app.config import settings

app = typer.Typer(add_completion=False, help="Automated job discovery pipeline")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("app")

NOT_IMPLEMENTED = "stage not yet implemented"


@app.command()
def collect() -> None:
    """Stage 1 — query configured boards, land raw output verbatim."""
    from app.db import session_scope
    from app.pipeline import run_collect, track_run

    with session_scope() as session, track_run(session) as run:
        total = run_collect(session, run)
        typer.echo(f"run {run.id}: collected {total} records")
        for site, count in sorted(run.counts_by_site.items()):
            typer.echo(f"  {site:<12} {count}")


@app.command()
def normalise(
    run_id: int = typer.Option(None, help="Run to normalise. Defaults to the latest."),
) -> None:
    """Stage 2 — fingerprint and deduplicate."""
    from sqlalchemy import select

    from app.db import session_scope
    from app.db.models import Run
    from app.pipeline import run_normalise

    with session_scope() as session:
        if run_id is None:
            run = session.scalar(select(Run).order_by(Run.started_at.desc()))
        else:
            run = session.get(Run, run_id)
        if run is None:
            typer.echo("no run found", err=True)
            raise typer.Exit(code=1)

        raw_count, distinct = run_normalise(session, run)
        typer.echo(f"run {run.id}: {raw_count} raw rows -> {distinct} distinct postings")


@app.command()
def score() -> None:
    """Stage 3 — title filter, then local model evaluation."""
    raise typer.Exit(code=_unimplemented("score"))


@app.command()
def publish() -> None:
    """Stage 4 — write records above threshold to Notion."""
    raise typer.Exit(code=_unimplemented("publish"))


@app.command("run-all")
def run_all() -> None:
    """Run every stage in order, recording per-stage counts."""
    from app.pipeline.runner import run_all_profiles

    result = run_all_profiles()
    typer.echo(
        f"run {result['run_id']}: collected={result['collected']} raw={result['raw']} "
        f"distinct={result['distinct']} suppressed={result['suppressed']}"
    )
    # Stages 3 and 4 join here once the CV is supplied
    typer.echo("stages 3-4 outstanding (scoring, publication)")


@app.command()
def status(limit: int = typer.Option(10, help="How many recent runs to show.")) -> None:
    """Recent runs and their per-stage counts.

    This is the weekly review surface (design §7.4): counts trending toward zero
    while status stays 'success' is the signal that a source has begun
    restricting access.
    """
    from sqlalchemy import select

    from app.db import session_scope
    from app.db.models import Run

    with session_scope() as session:
        runs = session.scalars(
            select(Run).order_by(Run.started_at.desc()).limit(limit)
        ).all()
        if not runs:
            typer.echo("no runs recorded")
            return

        typer.echo(f"{'id':>4}  {'started':<20} {'status':<9} {'coll':>5} {'dedup':>6}  by_site")
        for r in runs:
            started = r.started_at.strftime("%Y-%m-%d %H:%M:%S")
            by_site = ", ".join(f"{k}={v}" for k, v in sorted((r.counts_by_site or {}).items()))
            typer.echo(
                f"{r.id:>4}  {started:<20} {r.status:<9} "
                f"{r.collected_count:>5} {r.deduplicated_count:>6}  {by_site}"
            )
            if r.error:
                typer.echo(f"      error: {r.error}")


@app.command()
def serve() -> None:
    """Run the scheduler in the foreground (the container's default command).

    Each enabled search profile runs on its own schedule (US4, ADR-0005).
    """
    from app.pipeline.runner import run_one_profile
    from app.scheduler import build_scheduler

    scheduler = build_scheduler(run_one_profile)
    log.info("scheduler starting: one job per enabled profile (%s)", settings.timezone)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")


@app.command()
def web(
    host: str = typer.Option(None, help="Bind address. Defaults to configuration."),
    port: int = typer.Option(None, help="Port. Defaults to configuration."),
    reload: bool = typer.Option(False, help="Reload on source change (development)."),
) -> None:
    """Serve the triage interface (ADR-0004)."""
    import uvicorn

    uvicorn.run(
        "app.web.app:app",
        host=host or settings.web_host,
        port=port or settings.web_port,
        reload=reload,
    )


@app.command()
def config() -> None:
    """Print effective configuration, with secrets masked."""
    typer.echo(f"database_url      {_mask(settings.database_url)}")
    typer.echo(f"ollama_host       {settings.ollama_host}")
    typer.echo(f"scoring_model     {settings.scoring_model}")
    typer.echo(f"publish_threshold {settings.publish_threshold}")
    typer.echo(f"web               {settings.web_host}:{settings.web_port}")
    typer.echo(f"schedule          {settings.schedule_hour:02d}:"
               f"{settings.schedule_minute:02d} {settings.timezone}")
    typer.echo(f"searches          {len(settings.searches)}")
    for spec in settings.searches:
        remote = " remote" if spec.is_remote else ""
        typer.echo(f"  {spec.term!r} @ {spec.location!r} [{spec.country}]"
                   f"{remote} via {','.join(spec.sites)}")


def _unimplemented(stage: str) -> int:
    typer.echo(f"{stage}: {NOT_IMPLEMENTED}", err=True)
    return 1


def _mask(url: str) -> str:
    """Hide the password in a connection string."""
    if "@" not in url or "//" not in url:
        return url
    scheme, rest = url.split("//", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}//{user}:***@{host}"


if __name__ == "__main__":
    app()
