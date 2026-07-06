"""M1 self-serve accounts (§ Core 14): signup with invite code, login mints the API
token server-side, single-repo mode — signup auto-joins the server's default repo.
Nobody pastes tokens or repo ids; the login response carries both.
"""


import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.config import settings
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Member, Repo
from ctxvcs.store.repo_ops import create_repo, hash_token, issue_token, member_by_token

router = APIRouter()


class SignupBody(BaseModel):
    email: EmailStr
    password: str
    invite_code: str
    display_name: str = ""


class LoginBody(BaseModel):
    email: EmailStr
    password: str


def default_repo(session: Session) -> Repo:
    """Get-or-create the single-repo-mode default repo (bootstrapped lazily so a fresh
    deployment works before any admin action)."""
    cfg = settings()
    repo = session.execute(
        select(Repo).where(Repo.name == cfg.default_repo_name).order_by(Repo.created_at)
    ).scalars().first()
    if repo is None:
        repo, _tok = create_repo(session, cfg.default_repo_name, cfg.admin_email or "admin")
        session.commit()
        from ctxvcs.compiler.build import compile_pages

        compile_pages(session, repo.id, None)
    return repo


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings().bcrypt_rounds)).decode()


def _check_password(password: str, stored: str | None) -> bool:
    return bool(stored) and bcrypt.checkpw(password.encode(), stored.encode())


@router.post("/auth/signup")
def signup(body: SignupBody, session: Session = Depends(get_session)):
    cfg = settings()
    if not cfg.invite_code:
        raise HTTPException(403, "signup is disabled: the operator has not set an invite code")
    if body.invite_code != cfg.invite_code:
        raise HTTPException(403, "invalid invite code")
    if len(body.password) < 8:
        raise HTTPException(422, "password must be at least 8 characters")

    repo = default_repo(session)
    email = body.email.lower()
    existing = session.get(Member, (repo.id, email))
    if existing is not None and existing.password_hash:
        raise HTTPException(409, "already registered — log in instead")

    role = "owner" if (cfg.admin_email and email == cfg.admin_email.lower()) else "member"
    token = issue_token()
    if existing is None:
        existing = Member(repo_id=repo.id, principal=email, role=role)
        session.add(existing)
    existing.role = existing.role or role
    if role == "owner":
        existing.role = "owner"
    existing.password_hash = _hash_password(body.password)
    existing.display_name = body.display_name or email.split("@")[0]
    existing.api_token_hash = hash_token(token)
    session.commit()
    return {"token": token, "repo_id": str(repo.id), "role": existing.role,
            "display_name": existing.display_name}


@router.post("/auth/login")
def login(body: LoginBody, session: Session = Depends(get_session)):
    repo = default_repo(session)
    member = session.get(Member, (repo.id, body.email.lower()))
    if member is None or not _check_password(body.password, member.password_hash):
        raise HTTPException(401, "invalid email or password")
    # login mints/regenerates the API token (§ Core 14). Note: a new login invalidates
    # tokens from previous logins — one active credential per member in M1.
    token = issue_token()
    member.api_token_hash = hash_token(token)
    session.commit()
    return {"token": token, "repo_id": str(repo.id), "role": member.role,
            "display_name": member.display_name}


@router.get("/me")
def me(authorization: str | None = Header(default=None), session: Session = Depends(get_session)):
    from ctxvcs.api.deps import _token

    repo = default_repo(session)
    member = member_by_token(session, repo.id, _token(authorization))
    if member is None:
        raise HTTPException(401, "invalid token")
    return {"email": member.principal, "display_name": member.display_name,
            "role": member.role, "repo_id": str(repo.id)}


@router.get("/repo")
def repo_info(session: Session = Depends(get_session)):
    """Single-repo mode: the default repo's public identity (no auth — used by the
    signup page to show the team name)."""
    repo = default_repo(session)
    return {"repo_id": str(repo.id), "name": repo.name}
