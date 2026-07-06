"""M1 self-serve accounts (§ Core 14): signup/login/me in single-repo mode."""

import uuid

import pytest


@pytest.fixture
def client(session, monkeypatch):
    # unique default repo per test run — the shared dev DB stays clean
    monkeypatch.setenv("CTXVCS_DEFAULT_REPO_NAME", f"authtest-{uuid.uuid4().hex[:8]}")
    monkeypatch.setenv("CTXVCS_INVITE_CODE", "sesame")
    monkeypatch.setenv("CTXVCS_ADMIN_EMAIL", "admin@test.dev")
    monkeypatch.setenv("CTXVCS_EMBED_PROVIDER", "fake")
    from ctxvcs.config import settings

    settings.cache_clear()
    from fastapi.testclient import TestClient

    from ctxvcs.api.main import app

    yield TestClient(app)
    settings.cache_clear()


def test_signup_login_me_roundtrip(client):
    r = client.post("/auth/signup", json={
        "email": "Friend@Example.com", "password": "longenough1", "invite_code": "sesame",
        "display_name": "小明"})
    assert r.status_code == 200
    assert r.json()["role"] == "member"

    assert client.post("/auth/signup", json={
        "email": "friend@example.com", "password": "longenough1", "invite_code": "sesame"},
    ).status_code == 409  # duplicate

    login = client.post("/auth/login", json={"email": "friend@example.com", "password": "longenough1"})
    assert login.status_code == 200
    tok = login.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert me.json()["email"] == "friend@example.com"
    assert me.json()["display_name"] == "小明"


def test_rejections(client):
    assert client.post("/auth/login", json={"email": "ghost@x.dev", "password": "whatever1"},
                       ).status_code == 401
    assert client.post("/auth/signup", json={
        "email": "a@b.dev", "password": "longenough1", "invite_code": "wrong"}).status_code == 403
    assert client.post("/auth/signup", json={
        "email": "a@b.dev", "password": "short", "invite_code": "sesame"}).status_code == 422


def test_admin_email_gets_owner_role(client):
    r = client.post("/auth/signup", json={
        "email": "admin@test.dev", "password": "longenough1", "invite_code": "sesame"})
    assert r.json()["role"] == "owner"


def test_login_rotates_token(client):
    client.post("/auth/signup", json={
        "email": "rot@test.dev", "password": "longenough1", "invite_code": "sesame"})
    t1 = client.post("/auth/login", json={"email": "rot@test.dev", "password": "longenough1"}).json()["token"]
    t2 = client.post("/auth/login", json={"email": "rot@test.dev", "password": "longenough1"}).json()["token"]
    assert t1 != t2
    assert client.get("/me", headers={"Authorization": f"Bearer {t1}"}).status_code == 401
    assert client.get("/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200
