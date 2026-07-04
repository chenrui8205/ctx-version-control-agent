"""§14 invariants against a real Postgres: master≡HEAD, atomicity under injected
failure, identity rules, idempotent identical pushes, stale-parent rejection."""

import uuid

import pytest
from sqlalchemy import select, text

from ctxvcs.dag.trees import commit_tree, head_commit, master_tree
from ctxvcs.llm.fakes import FakeEmbedder, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.commit_txn import CommitError, StaleParentError, commit_staged
from ctxvcs.store.models import StagedEntries
from ctxvcs.store.repo_ops import current_schema


def _ctx(session, repo, script=None):
    return PipelineContext(
        session=session,
        embedder=FakeEmbedder(),
        reconciler=ScriptedReconcileClient(script or {}),
        entry_types=current_schema(session, repo.id).entry_types,
    )


def _raw(key, subject, body, type_="finding", fields=None, ts="2026-06-20"):
    return {"type": type_, "subject": subject, "fields": fields or {}, "body": body,
            "provenance": {"origin": "agent", "ts": ts, "fixture_key": key}}


def _stage_and_commit(session, repo, raws, script=None, summary="s"):
    ctx = _ctx(session, repo, script)
    state = run_stage(ctx, repo.id, "tester", raws, summary)
    assert state["merge_status"] == "clean", state
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed", cstate
    return cstate["commit_hash"]


def test_master_equals_head_after_every_commit(session, repo):
    n = uuid.uuid4().hex[:8]
    _stage_and_commit(session, repo, [_raw("a", f"subj-{n}", f"first fact {n}")])
    assert master_tree(session, repo.id) == commit_tree(session, head_commit(session, repo.id))
    _stage_and_commit(session, repo, [_raw("b", f"subj2-{n}", f"second fact {n}")])
    assert master_tree(session, repo.id) == commit_tree(session, head_commit(session, repo.id))


def test_identical_push_is_zero_new_rows(session, repo):
    n = uuid.uuid4().hex[:8]
    raws = [_raw("a", f"subj-{n}", f"a stable fact {n}")]
    _stage_and_commit(session, repo, raws)
    tree0 = master_tree(session, repo.id)
    count0 = session.execute(text("SELECT count(*) FROM entries")).scalar()

    ctx = _ctx(session, repo)
    state = run_stage(ctx, repo.id, "tester", raws, "again")
    actions = state["proposed_actions"]
    assert [a["action"] for a in actions] == ["drop"]
    assert actions[0]["path"] == "exact"  # deterministic, no LLM
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "error"  # empty commit refused
    assert master_tree(session, repo.id) == tree0
    assert session.execute(text("SELECT count(*) FROM entries")).scalar() == count0


def test_supersede_keeps_entry_id_and_marks_provenance(session, repo):
    n = uuid.uuid4().hex[:8]
    subj = f"svc-{n}"
    _stage_and_commit(session, repo, [_raw("v1", subj, f"timeout is 60 {n}", fields={"t": 60})])
    tree0 = master_tree(session, repo.id)
    (eid, old_hash), = tree0.items()

    script = {(f"v2", f"v1"): "refines"}
    ctx = _ctx(session, repo, script)
    state = run_stage(ctx, repo.id, "tester",
                      [_raw("v2", subj, f"changed timeout 60 to 30 {n}", fields={"t": 30},
                            ts="2026-06-30")], "update")
    assert [a["action"] for a in state["proposed_actions"]] == ["supersede"]
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed"

    tree1 = master_tree(session, repo.id)
    assert set(tree1) == {eid}  # identity preserved, no aliasing (§ Core 9)
    assert tree1[eid] != old_hash
    prov = session.execute(text("SELECT provenance FROM entries WHERE content_hash=:h"),
                           {"h": old_hash}).scalar()
    assert prov.get("superseded_by", {}).get("content_hash") == tree1[eid]


def test_commit_atomicity_under_injected_failure(session, repo):
    n = uuid.uuid4().hex[:8]
    ctx = _ctx(session, repo)
    state = run_stage(ctx, repo.id, "tester", [_raw("a", f"subj-{n}", f"fact {n}")], "s")
    staged = session.get(StagedEntries, uuid.UUID(state["staging_id"]))

    ref0 = head_commit(session, repo.id)
    tree0 = master_tree(session, repo.id)
    commits0 = session.execute(text("SELECT count(*) FROM commits")).scalar()

    class Boom(Exception):
        pass

    def failpoint(step):
        if step == "ref":
            raise Boom()

    with pytest.raises(Boom):
        commit_staged(session, staged, failpoint=failpoint)

    # failure before ref advance leaves refs/master_entries untouched (§4.3)
    assert head_commit(session, repo.id) == ref0
    assert master_tree(session, repo.id) == tree0
    assert session.execute(text("SELECT count(*) FROM commits")).scalar() == commits0

    # and the staging is still committable afterwards
    session.refresh(staged)
    result = commit_staged(session, staged)
    assert head_commit(session, repo.id) == result.commit_hash


def test_stale_parent_rejected(session, repo):
    n = uuid.uuid4().hex[:8]
    ctx = _ctx(session, repo)
    s1 = run_stage(ctx, repo.id, "t1", [_raw("a", f"s1-{n}", f"fact one {n}")], "one")
    s2 = run_stage(ctx, repo.id, "t2", [_raw("b", f"s2-{n}", f"fact two {n}")], "two")
    assert run_commit(ctx, uuid.UUID(s1["staging_id"]))["merge_status"] == "committed"

    staged2 = session.get(StagedEntries, uuid.UUID(s2["staging_id"]))
    with pytest.raises(StaleParentError):
        commit_staged(session, staged2)


def test_conflict_blocks_commit_until_resolved(session, repo):
    n = uuid.uuid4().hex[:8]
    subj = f"svc-{n}"
    _stage_and_commit(session, repo, [_raw("v1", subj, f"timeout is 60 {n}", fields={"t": 60})])
    script = {("v2", "v1"): "contradicts"}
    ctx = _ctx(session, repo, script)
    state = run_stage(ctx, repo.id, "tester",
                      [_raw("v2", subj, f"timeout is 30 {n}", fields={"t": 30}, ts="2026-06-30")], "x")
    assert state["merge_status"] == "needs_review"
    assert state["merge_request_id"] is not None
    tree0 = master_tree(session, repo.id)

    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "needs_review"  # refused without resolutions
    assert master_tree(session, repo.id) == tree0
