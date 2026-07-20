"""Engine and session management."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    # Verify liveness before use; the app container outlives many idle periods
    pool_pre_ping=True,
    future=True,
)

SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_session() -> Session:
    """Return a new session. Caller owns the lifecycle."""
    return SessionFactory()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on exception."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
