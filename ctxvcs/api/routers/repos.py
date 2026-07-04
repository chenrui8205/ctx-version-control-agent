import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ctxvcs.api.deps import require_member, require_owner
from ctxvcs.compiler.build import compile_pages
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Member
from ctxvcs.store.repo_ops import (
    add_member,
    add_schema_version,
    create_repo,
    current_schema,
    subject_registry,
)

router = APIRouter()


class RepoCreate(BaseModel):
    name: str
    owner: str


class MemberCreate(BaseModel):
    principal: str
    role: str = "member"


@router.post("/repos")
def post_repo(body: RepoCreate, session: Session = Depends(get_session)):
    """Bootstrap endpoint (unauthenticated in M0): creates repo + owner token,
    seeds the §3 default schema and the index/journal/open-threads pages."""
    repo, token = create_repo(session, body.name, body.owner)
    session.commit()
    compile_pages(session, repo.id, None)
    return {"repo_id": str(repo.id), "token": token}


@router.post("/repos/{r}/members")
def post_member(
    r: uuid.UUID,
    body: MemberCreate,
    session: Session = Depends(get_session),
    _owner: Member = Depends(require_owner),
):
    token = add_member(session, r, body.principal, body.role)
    session.commit()
    return {"principal": body.principal, "role": body.role, "token": token}


@router.get("/repos/{r}/schema")
def get_schema(r: uuid.UUID, session: Session = Depends(get_session),
               _m: Member = Depends(require_member)):
    sv = current_schema(session, r)
    return {"version": sv.version, "entry_types": sv.entry_types}


@router.post("/repos/{r}/schema")
def post_schema(r: uuid.UUID, body: dict, session: Session = Depends(get_session),
                _owner: Member = Depends(require_owner)):
    entry_types = body.get("entry_types")
    if not isinstance(entry_types, dict) or not entry_types:
        raise HTTPException(422, "body must carry {entry_types: {...}}")
    v = add_schema_version(session, r, entry_types)
    session.commit()
    return {"version": v}


@router.get("/repos/{r}/subjects")
def get_subjects(r: uuid.UUID, session: Session = Depends(get_session),
                 _m: Member = Depends(require_member)):
    return {"subjects": subject_registry(session, r)}
