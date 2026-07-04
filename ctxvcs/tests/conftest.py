import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("CTXVCS_EMBED_PROVIDER", "fake")

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for `evals` imports


def _db_available() -> bool:
    try:
        from ctxvcs.store.db import engine

        with engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_DB_OK = _db_available()


@pytest.fixture
def session():
    if not _DB_OK:
        pytest.skip("postgres not available (docker compose up -d)")
    from ctxvcs.store.db import session_factory

    with session_factory()() as s:
        yield s


@pytest.fixture
def repo(session):
    from ctxvcs.store.repo_ops import create_repo

    repo, token = create_repo(session, f"test-{uuid.uuid4().hex[:8]}", "tester")
    session.commit()
    from ctxvcs.compiler.build import compile_pages

    compile_pages(session, repo.id, None)
    return repo
