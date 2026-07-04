"""Compiler invariants (§14): byte-stable recompiles, memoization (unchanged input
hash ⇒ zero writes), rebuild-from-scratch equivalence."""

import uuid

from sqlalchemy import text

from ctxvcs.compiler.build import compile_pages, search_pages, serve_page
from ctxvcs.llm.fakes import FakeEmbedder, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.repo_ops import current_schema


def _push(session, repo, raws, script=None):
    ctx = PipelineContext(
        session=session, embedder=FakeEmbedder(),
        reconciler=ScriptedReconcileClient(script or {}),
        entry_types=current_schema(session, repo.id).entry_types,
        after_commit=lambda _h, changed: compile_pages(session, repo.id, changed),
    )
    state = run_stage(ctx, repo.id, "tester", raws, "test session")
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed"


def _raw(key, subject, body, type_="finding", fields=None, ts="2026-06-20"):
    return {"type": type_, "subject": subject, "fields": fields or {}, "body": body,
            "provenance": {"origin": "agent", "ts": ts, "author": "tester", "fixture_key": key}}


def _pages(session, repo):
    rows = session.execute(
        text("SELECT slug, content, input_hash FROM wiki_pages WHERE repo_id=:r"),
        {"r": str(repo.id)},
    ).mappings()
    return {r["slug"]: (r["input_hash"], r["content"]) for r in rows}


def test_noop_recompile_writes_nothing(session, repo):
    n = uuid.uuid4().hex[:8]
    _push(session, repo, [_raw("a", f"cache-{n}", f"the cache holds bans {n}",
                               fields={"ttl_minutes": 15})])
    written = compile_pages(session, repo.id, [])
    assert written == []  # memoization: unchanged input hash ⇒ zero writes


def test_rebuild_reproduces_byte_identical_pages(session, repo):
    n = uuid.uuid4().hex[:8]
    _push(session, repo, [
        _raw("a", f"cache-{n}", f"the cache holds bans, see [[queue-{n}]] {n}", fields={"ttl_minutes": 15}),
        _raw("b", f"queue-{n}", f"queue depth alarm at 10k {n}", type_="constraint",
             fields={"kind": "technical", "hard": True}),
        _raw("c", f"steps-{n}", f"wire the alarm {n}", type_="next_step", fields={"status": "open"}),
    ])
    before = _pages(session, repo)
    session.execute(text("DELETE FROM wiki_pages WHERE repo_id=:r"), {"r": str(repo.id)})
    session.commit()
    compile_pages(session, repo.id, None)
    after = _pages(session, repo)
    assert set(before) == set(after)
    for slug in before:
        assert before[slug][1] == after[slug][1], f"{slug} not byte-identical"
        assert before[slug][0] == after[slug][0]


def test_sections_and_serve_and_search(session, repo):
    n = uuid.uuid4().hex[:8]
    _push(session, repo, [_raw("a", f"bloom-{n}", f"bloom filter sized for zebras {n}",
                               fields={"fpr": "0.1%"})])
    page = serve_page(session, repo.id, f"bloom-{n}")
    assert page is not None and page["kind"] == "subject"
    assert any(s["id"] == "facts" for s in page["sections"])
    section = serve_page(session, repo.id, f"bloom-{n}", section="facts")
    assert section["content"].startswith("## Facts")
    hits = search_pages(session, repo.id, "zebras")
    assert any(h["slug"] == f"bloom-{n}" for h in hits)


def test_dirty_tracking_bounds_recompiles(session, repo):
    n = uuid.uuid4().hex[:8]
    _push(session, repo, [
        _raw("a", f"alpha-{n}", f"alpha fact {n}"),
        _raw("b", f"beta-{n}", f"beta fact {n}"),
    ])
    before = _pages(session, repo)
    _push(session, repo, [_raw("c", f"alpha-{n}", f"alpha addendum {n}", type_="constraint",
                               fields={"kind": "technical", "hard": False})])
    after = _pages(session, repo)
    assert before[f"beta-{n}"] == after[f"beta-{n}"]  # untouched subject: same hash + bytes
    assert before[f"alpha-{n}"] != after[f"alpha-{n}"]
