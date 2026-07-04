"""M0 auth: repo membership + per-user API tokens (§ Core 14). Label RLS is M1."""

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ctxvcs.store.db import get_session
from ctxvcs.store.models import Member
from ctxvcs.store.repo_ops import member_by_token


def _token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def require_member(
    r: uuid.UUID,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Member:
    m = member_by_token(session, r, _token(authorization))
    if m is None:
        raise HTTPException(403, "not a member of this repo")
    return m


def require_owner(member: Member = Depends(require_member)) -> Member:
    if member.role != "owner":
        raise HTTPException(403, "owner role required")
    return member
