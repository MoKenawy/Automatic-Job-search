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


@app.command("filter")
def filter_(
    run_id: int = typer.Option(None, help="Run to filter. Defaults to the latest."),
    all_postings: bool = typer.Option(
        False, "--all", help="Re-apply the criteria to every posting, not just one run's."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would change, and write nothing."
    ),
) -> None:
    """Relevance and experience filter — record a verdict per posting (ADR-0016).

    Named `filter` for the operator; the function is `filter_` because the
    command name would otherwise shadow the builtin, the same reason `run-all`
    is declared separately from `run_all`.

    `--all` is how a criteria change reaches already-collected postings, with no
    board contacted (FR-011). It writes no run counters: those belong to a run
    that evaluated postings during an execution.
    """
    from sqlalchemy import select

    from app.config import RunConfig
    from app.db import session_scope
    from app.db.models import Run
    from app.pipeline import filter_all, run_filter

    if all_postings and run_id is not None:
        typer.echo("--all filters every posting; it cannot be combined with --run-id", err=True)
        raise typer.Exit(code=2)

    with session_scope() as session:
        config = RunConfig.resolve(session)

        if all_postings:
            outcome = filter_all(session, config, dry_run=dry_run)
            scope = "all postings"
        else:
            if run_id is None:
                run = session.scalar(select(Run).order_by(Run.started_at.desc()))
            else:
                run = session.get(Run, run_id)
            if run is None:
                typer.echo("no run found", err=True)
                raise typer.Exit(code=1)
            outcome = run_filter(session, run, config, dry_run=dry_run)
            scope = f"run {run.id}"

        prefix = "would change" if dry_run else "changed"
        typer.echo(
            f"{scope}: {outcome.passed} passed, {outcome.rejected} rejected, "
            f"{prefix} {outcome.changed} verdict(s)"
        )
        # Zero changes on a re-application is the point, not an absence of news:
        # it is how SC-007's "re-applying produces identical verdicts" is read
        # off the command rather than inferred.
        if not outcome.changed and outcome.evaluated:
            typer.echo("  verdicts already current — nothing was written")
        for fault in outcome.faults:
            typer.echo(f"  fault: {fault}", err=True)


@app.command()
def score() -> None:
    """Stage 3 — local model evaluation of the postings the filter admitted."""
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
        f"distinct={result['distinct']} passed={result['passed']} "
        f"rejected={result['rejected']}"
    )
    # Scoring and publication join here once the CV is supplied
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
        runs = session.scalars(select(Run).order_by(Run.started_at.desc()).limit(limit)).all()
        if not runs:
            typer.echo("no runs recorded")
            return

        typer.echo(
            f"{'id':>4}  {'started':<20} {'status':<9} {'coll':>5} {'dedup':>6} "
            f"{'pass':>5} {'rej':>5}  by_site"
        )
        for r in runs:
            started = r.started_at.strftime("%Y-%m-%d %H:%M:%S")
            by_site = ", ".join(f"{k}={v}" for k, v in sorted((r.counts_by_site or {}).items()))
            # A run the filter never touched prints —, not 0: zero would claim
            # the filter admitted nothing, which is a different fact and the
            # kind of false alarm this very table exists to raise honestly.
            filtered = r.filter_passed_count or r.filter_rejected_count
            passed = f"{r.filter_passed_count}" if filtered else "—"
            rejected = f"{r.filter_rejected_count}" if filtered else "—"
            typer.echo(
                f"{r.id:>4}  {started:<20} {r.status:<9} "
                f"{r.collected_count:>5} {r.deduplicated_count:>6} "
                f"{passed:>5} {rejected:>5}  {by_site}"
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
    typer.echo(
        f"schedule          {settings.schedule_hour:02d}:"
        f"{settings.schedule_minute:02d} {settings.timezone}"
    )
    typer.echo(f"searches          {len(settings.searches)}")
    for spec in settings.searches:
        remote = " remote" if spec.is_remote else ""
        typer.echo(
            f"  {spec.term!r} @ {spec.location!r} [{spec.country}]"
            f"{remote} via {','.join(spec.sites)}"
        )


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
