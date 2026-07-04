from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ctxvcs.config import settings

_engine = None
_session_factory = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings().database_url, pool_pre_ping=True)
    return _engine


def session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine(), expire_on_commit=False)
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_factory()() as s:
        yield s
