import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

_ENGINE: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


# PUBLIC_INTERFACE
def get_database_url() -> str:
    """Return the database URL from env.

    Environment:
      - DATABASE_URL: PostgreSQL DSN (e.g. postgresql://user:pass@host:5432/db)

    Returns:
      The DSN string.

    Raises:
      RuntimeError: if DATABASE_URL is missing.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Please configure it in the container .env."
        )
    return db_url


def _init_engine() -> None:
    """Initialize the SQLAlchemy engine and sessionmaker (singleton)."""
    global _ENGINE, _SessionLocal
    if _ENGINE is not None and _SessionLocal is not None:
        return

    db_url = get_database_url()
    # SQLAlchemy's create_engine is thread-safe; SessionLocal creates per-request sessions.
    _ENGINE = create_engine(
        db_url,
        pool_pre_ping=True,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Get the singleton SQLAlchemy Engine."""
    _init_engine()
    assert _ENGINE is not None
    return _ENGINE


# PUBLIC_INTERFACE
def get_sessionmaker() -> sessionmaker:
    """Get the singleton SQLAlchemy sessionmaker."""
    _init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


# PUBLIC_INTERFACE
@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session in a context manager.

    Commits on success, rolls back on error.
    """
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# PUBLIC_INTERFACE
def check_db_connection() -> None:
    """Validate DB connectivity with a lightweight SELECT 1.

    Raises:
      SQLAlchemyError: if the connection is not usable.
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise
