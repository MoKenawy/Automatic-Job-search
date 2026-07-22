"""Data model — four entities, per design §8.

Column choices are grounded in the measured JobSpy output of 20 July 2026
(design §4.3), not in the library's declared schema. JobSpy emits 34 columns, but
most are null for the two sources that work. Fields measured at 0% populated are
left in the raw payload rather than promoted to columns:

    salary block (salary_source, interval, min_amount, max_amount, currency)  D13
    job_level, job_function, listing_type       LinkedIn-declared, never populated
    company_industry, skills, experience_range  Naukri/LinkedIn-specific
    company_rating, company_reviews_count       Naukri-specific
    vacancy_count, work_from_home_type          Naukri-specific

Company enrichment (num_employees, revenue, description) *is* populated by Indeed
at roughly 60-70%, and is an attribute of the employer rather than the posting,
so it lives on `employers`.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB in production; degrades to JSON on other dialects (e.g. SQLite under
# test) so the model stays loadable without a PostgreSQL connection.
JSONB = _PG_JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


# Triage states (design §8.1). REJECTED doubles as the D9 suppression signal.
STATUS_NEW = "new"
STATUS_SHORTLIST = "shortlist"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_NEW, STATUS_SHORTLIST, STATUS_APPLIED, STATUS_REJECTED)


class Employer(Base):
    """Normalised employer records."""

    __tablename__ = "employers"
    __table_args__ = (
        # Partial index supporting blacklist suppression (US3); only the few
        # suppressed rows are indexed. Declared here so autogenerate does not treat
        # the migration-created index as orphaned.
        Index(
            "ix_employers_suppressed",
            "suppressed",
            postgresql_where=text("suppressed"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    # Legal-entity suffixes stripped; descriptor words such as Technologies,
    # Solutions or Group deliberately retained (design §7.3)
    normalised_name: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )

    # Opportunistic enrichment, populated by Indeed where available
    url: Mapped[str | None] = mapped_column(String(1024))
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    num_employees: Mapped[str | None] = mapped_column(String(64))
    revenue: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    # Excludes an employer permanently from publication
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    postings: Mapped[list["Posting"]] = relationship(back_populates="employer")


class Run(Base):
    """One record per execution.

    Per-stage counts are the mechanism by which silent collection decay becomes
    visible: counts trending toward zero while status remains 'success' is the
    signal to investigate (design §7.4).
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)

    # The search profile that triggered this run (US4). Null for a manual run-all
    # over every profile. Additive and nullable.
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="SET NULL"), index=True
    )

    collected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deduplicated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filter_passed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filter_rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scored_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Per-source collected counts, e.g. {"indeed": 40, "linkedin": 0}.
    # A single source falling to zero is invisible in the aggregate above.
    counts_by_site: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    error: Mapped[str | None] = mapped_column(Text)

    raw_postings: Mapped[list["RawPosting"]] = relationship(back_populates="run")


class RawPosting(Base):
    """Append-only landing zone.

    Verbatim collector output, retained for reprocessing and diagnosis. No
    transformation or deduplication applied (design §8). Holding the full row
    means a later decision to promote a field costs a backfill, not a re-scrape.
    """

    __tablename__ = "raw_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False
    )

    site: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Board-assigned identifier, e.g. 'in-2e722464351d632c'. Not unique across boards.
    site_job_id: Mapped[str | None] = mapped_column(String(256), index=True)

    # The complete JobSpy row, all 34 columns, nulls included
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["Run"] = relationship(back_populates="raw_postings")


class Posting(Base):
    """One record per real-world role, keyed on fingerprint.

    Fingerprint is derived from normalised employer, normalised title and country
    (design D12, §7.3.1). City is deliberately not an input: boards localise city
    names irreconcilably, so including it guarantees the duplicates the fingerprint
    exists to prevent.
    """

    __tablename__ = "postings"
    __table_args__ = (
        # The list view's query: published, ranked by score, filtered by status
        Index("ix_postings_triage_queue", "published", "status", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    employer_id: Mapped[int] = mapped_column(
        ForeignKey("employers.id"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalised_title: Mapped[str] = mapped_column(String(512), nullable=False)

    # Verbatim from the first board to surface the role, retained for display.
    # Format differs per board ('القاهرة, C, EG' vs 'Cairo, Egypt') and is NOT
    # comparable across sources — see country_code for the comparable value.
    location_raw: Mapped[str | None] = mapped_column(String(256))
    # ISO 3166-1 alpha-2, parsed from location_raw. The fingerprint input.
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    description: Mapped[str | None] = mapped_column(Text)
    # JobSpy returns datetime.date, not datetime
    date_posted: Mapped[date | None] = mapped_column(Date, index=True)
    job_type: Mapped[str | None] = mapped_column(String(64))

    # Provenance: which boards surfaced this role and the URL for each, e.g.
    # {"indeed": {"url": "...", "job_id": "...", "first_seen": "..."}, ...}
    sources: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Stage 3 — coarse title filter, then model evaluation
    title_filter_passed: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[int | None] = mapped_column(Integer, index=True)
    matched_skills: Mapped[list | None] = mapped_column(JSONB)
    gaps: Mapped[list | None] = mapped_column(JSONB)
    rationale: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Model that produced the score, so a prompt or model change is traceable
    scored_by_model: Mapped[str | None] = mapped_column(String(128))

    # Stage 4 — publication. After D15 this is a state transition rather than a
    # write to an external service.
    published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Triage state (design §8.1). REJECTED is the suppression mechanism required
    # by D9: the record is retained indefinitely and never resurfaces, so no
    # separate suppression flag is needed on the posting.
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_NEW, nullable=False, index=True
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employer: Mapped["Employer"] = relationship(back_populates="postings")


class SearchProfile(Base):
    """A saved, individually scheduled job-survey definition (US4, ADR-0005).

    Supersedes the SEARCHES environment list. One collector invocation per
    profile; each carries its own schedule and can be enabled/disabled.
    """

    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    term: Mapped[str] = mapped_column(String(256), nullable=False)
    location: Mapped[str | None] = mapped_column(String(256))
    country: Mapped[str] = mapped_column(String(64), default="egypt", nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Subset of working boards, e.g. ["indeed", "linkedin"]
    sites: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Advisory until wired into the scorer (research Q1); a post-collection filter,
    # not a board parameter
    experience: Mapped[str | None] = mapped_column(String(64))

    schedule_hour: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    schedule_minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AppSetting(Base):
    """Runtime-editable operational configuration (US4, ADR-0005).

    Key–value; the key matches a field on the Settings model. Read resolution:
    app_settings value → environment/.env default → code default. Secrets and
    restart-only settings are never stored here.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
