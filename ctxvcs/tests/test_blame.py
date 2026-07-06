"""M1 blame (§9/§14): deterministic — the S4 dogfood story must be fully recoverable.

Timeline under test: alex sets v=60 (agent) → riley changes it to 30 with change
language (human, supersede) → alex2 asserts 50 as current (contradicts, MR) →
admin resolves keep_existing. Blame must name every actor, the mechanism each
version landed by, the rejected challenge, and who decided.
"""

import uuid

from sqlalchemy import select

from ctxvcs.config import settings
from ctxvcs.dag.blame import blame_entry
from ctxvcs.dag.trees import master_tree
from ctxvcs.llm.fakes import FakeEmbedder, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.models import Conflict
from ctxvcs.store.repo_ops import current_schema


def _ctx(session, repo, script):
    return PipelineContext(
        session=session, embedder=FakeEmbedder(settings().embed_dim),
        reconciler=ScriptedReconcileClient(script),
        entry_types=current_schema(session, repo.id).entry_types,
    )


NONCE = uuid.uuid4().hex[:8]  # content-isolate runs against the shared dev DB
# (the entries store is global/content-addressed — identical bodies across runs
# would share the FIRST run's provenance row; scenario_lib nonces for the same reason)


def _entry(key, type_, fields, body, origin):
    return {"type": type_, "subject": "timeout", "fields": fields,
            "body": f"{body} [run {NONCE}]",
            "provenance": {"ts": "2026-07-05", "origin": origin, "fixture_key": key}}


def _push(session, repo, script, author, entries, resolutions=None):
    ctx = _ctx(session, repo, script)
    state = run_stage(ctx, repo.id, author, entries, f"{author} push")
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]), resolutions)
    return state, cstate


def test_blame_recovers_the_full_story(session, repo):
    # v1: alex's agent records 60
    _push(session, repo, {}, "alex",
          [_entry("v60", "finding", {"timeout_seconds": 60, "confidence": "high"},
                  "Timeout is 60s.", "agent")])
    (eid,) = master_tree(session, repo.id)

    # v2: riley changes it to 30 (clean supersede)
    _push(session, repo, {("v30", "v60"): "refines"}, "riley",
          [_entry("v30", "state_change", {"timeout_seconds": 30, "what_changed": "60 -> 30"},
                  "Changed timeout from 60s to 30s after load test.", "human")])

    # v3 attempt: alex2 asserts 50 as current -> contradicts -> admin keeps existing
    ctx = _ctx(session, repo, {("v50", "Changed timeout from 60s to 30s after load test."): "contradicts"})
    state = run_stage(ctx, repo.id, "alex2",
                      [_entry("v50", "finding", {"timeout_seconds": 50}, "Timeout is 50s.", "agent")],
                      "stale assert")
    assert state["merge_status"] == "needs_review"
    conflict = session.execute(select(Conflict).where(Conflict.repo_id == repo.id)).scalars().one()
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]),
                        {str(conflict.id): {"action": "keep_existing", "decided_by": "boss",
                                            "note": "riley's change is deliberate; 50 is stale"}})
    # nothing else lands (the only entry was rejected) but the resolution itself
    # commits — otherwise the MR would roll back and stay open forever
    assert cstate["merge_status"] == "committed"

    b = blame_entry(session, repo.id, eid)
    assert b["subject_key"] == "timeout"
    assert [v["author"] for v in b["versions"]] == ["riley", "alex"]
    assert [v["origin"] for v in b["versions"]] == ["human", "agent"]

    current, original = b["versions"]
    assert current["landed"]["via"] == "supersede"
    assert current["landed"]["relation"] == "refines"
    assert original["landed"]["via"] == "new"

    # the challenge: alex2's 50 was rejected by boss, and blame says so
    (challenge,) = current["challenges"]
    assert challenge["challenger"] == "alex2"
    assert challenge["challenged_fields"] == {"timeout_seconds": 50}
    assert challenge["decided"] == "keep_existing"
    assert challenge["decided_by"] == "boss"
    assert challenge["status"] == "resolved"

    # per-field: the current value 30 was introduced by riley's commit, not alex's
    f = b["fields"]["timeout_seconds"]
    assert f["value"] == 30
    assert f["introduced_in"]["author"] == "riley"
    assert f["introduced_in"]["commit"] == current["commit"]


def test_blame_is_stable_and_survives_rebuild(session, repo):
    _push(session, repo, {}, "sam",
          [_entry("only", "constraint", {"kind": "technical", "hard": True},
                  "Integer cents only.", "human")])
    (eid,) = master_tree(session, repo.id)
    b1 = blame_entry(session, repo.id, eid)
    from ctxvcs.compiler.build import compile_pages

    compile_pages(session, repo.id, None)  # full rebuild must not affect blame
    b2 = blame_entry(session, repo.id, eid)
    assert b1 == b2
    assert b1["versions"][0]["landed"]["via"] == "new"


def test_blame_unknown_entry_returns_none(session, repo):
    assert blame_entry(session, repo.id, uuid.uuid4()) is None
