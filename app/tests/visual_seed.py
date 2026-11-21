"""Fixed seed for the visual gate (006 FR-026, research R7).

Deterministic by construction: every timestamp is an offset from the fixed ANCHOR, and
the visual test freezes the shell clock to ANCHOR, so neither absolute dates nor "2d ago"
drift with the wall clock.
Covers every status, Arabic and very long employer names, a filtered-out posting,
runs in all three states, two profiles, a blacklisted employer and source health.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import (
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
    Employer,
    Posting,
    Run,
    SearchProfile,
)

STATUS_APPLIED = "applied"
ANCHOR = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
LONG_NAME = "International Consolidated Engineering and Technology Solutions Holding Company"


def seed(db: Session) -> int:
    """Populate `db`; return the id of the posting used for the detail page."""
    now = ANCHOR
    p1 = SearchProfile(name="Data engineering", term="data engineer", sites=["indeed", "linkedin"])
    p2 = SearchProfile(
        name="Remote analytics", term="analytics engineer", is_remote=True, sites=["linkedin"]
    )
    db.add_all([p1, p2])
    db.flush()

    employers = [
        Employer(name="PwC", normalised_name="pwc"),
        Employer(name="شركة النيل للتقنية", normalised_name="شركه النيل للتقنيه"),
        Employer(name=LONG_NAME, normalised_name="international consolidated"),
        Employer(name="Blocked Corp", normalised_name="blocked corp", suppressed=True),
    ]
    db.add_all(employers)
    db.flush()

    runs = [
        Run(
            status="success",
            started_at=now - timedelta(hours=3, minutes=10),
            finished_at=now - timedelta(hours=3),
            profile_id=p1.id,
            collected_count=53,
            deduplicated_count=36,
            filter_passed_count=30,
            filter_rejected_count=6,
            counts_by_site={"indeed": 30, "linkedin": 23},
        ),
        Run(
            status="failed",
            started_at=now - timedelta(days=1, hours=2),
            finished_at=now - timedelta(days=1, hours=2) + timedelta(minutes=2),
            profile_id=p2.id,
            error="Board returned HTTP 429",
            counts_by_site={"linkedin": 0},
        ),
        Run(
            status="running",
            started_at=now - timedelta(minutes=5),
            profile_id=p1.id,
            counts_by_site={"indeed": 4},
        ),
    ]
    db.add_all(runs)

    specs = [
        ("Senior Data Engineer", 0, STATUS_NEW, 91, "EG", False, True),
        ("ETIC, Data Engineer, Senior Associate", 0, STATUS_SHORTLIST, 78, "EG", False, True),
        ("مهندس بيانات", 1, STATUS_APPLIED, 64, "EG", False, True),
        ("Analytics Engineer " + "(Platform) " * 6, 2, STATUS_NEW, 55, "AE", True, True),
        ("Junior Data Developer", 0, STATUS_REJECTED, None, "EG", False, True),
        ("Data Analyst", 2, STATUS_NEW, None, "EG", False, False),
    ]
    first_id = 0
    for i, (title, emp, status, score, cc, remote, passed) in enumerate(specs):
        posting = Posting(
            fingerprint=f"{i:064d}",
            employer_id=employers[emp].id,
            title=title,
            normalised_title=title.lower(),
            location_raw="Cairo, Egypt" if cc == "EG" else "Dubai, UAE",
            country_code=cc,
            is_remote=remote,
            description="Build and operate batch and streaming pipelines.\n\nSQL, Python, Airflow.",
            date_posted=(now - timedelta(days=2 + i)).date(),
            job_type="fulltime",
            sources={
                "indeed": {"url": f"https://example.test/i/{i}"},
                "linkedin": {"url": f"https://example.test/l/{i}"},
            },
            score=score,
            rationale="Strong overlap with the CV." if score else None,
            matched_skills=["SQL", "Python"] if score else None,
            gaps=["Scala"] if score else None,
            published=score is not None,
            status=status,
            title_filter_passed=passed,
            experience_filter_passed=passed,
            first_seen_at=now - timedelta(days=2 + i),
            last_retrieved_at=now - timedelta(hours=3),
        )
        db.add(posting)
        db.flush()
        first_id = first_id or posting.id
    db.commit()
    return first_id
