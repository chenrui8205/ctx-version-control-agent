"""§6 deterministic routing rules (2026-07-04, dogfood DF-1/2/4) + §14 invariants.

Rule 1: an x-lifecycle entry may only be superseded by its own type — any cross-type
        refines/subsumes verdict is downgraded to keep-both.
Rule 2: apply_actions never executes two supersedes against one target entry_id in a
        batch; extras fail closed into ambiguous_supersede conflicts (needs_review).
Backstop: commit_staged raises rather than let a second supersede silently destroy
        the first (last-writer-wins is an unlabeled drop).
"""

import uuid

from sqlalchemy import select

from ctxvcs.config import settings
from ctxvcs.llm.fakes import FakeEmbedder, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.commit_txn import CommitError, commit_staged
from ctxvcs.store.models import Conflict, StagedEntries
from ctxvcs.store.repo_ops import current_schema


def _ctx(session, repo, script):
    return PipelineContext(
        session=session,
        embedder=FakeEmbedder(settings().embed_dim),
        reconciler=ScriptedReconcileClient(script),
        entry_types=current_schema(session, repo.id).entry_types,
    )


def _entry(key, type_, subject, fields, body, origin="human"):
    return {"type": type_, "subject": subject, "fields": fields, "body": body,
            "provenance": {"ts": "2026-07-04", "origin": origin, "fixture_key": key}}


def _seed(session, repo, entries):
    ctx = _ctx(session, repo, {})
    state = run_stage(ctx, repo.id, "seeder", entries, "seed")
    assert state["merge_status"] == "clean"
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed"
    return cstate


def test_cross_type_supersede_of_lifecycle_entry_downgrades_to_keep(session, repo):
    _seed(session, repo, [_entry("q", "open_question", "cents",
                                 {"status": "open", "blocking": True}, "How to split leftover cents?")])
    # script the DF-1b misclassification: decision refines question
    ctx = _ctx(session, repo, {("dec", "q"): "refines"})
    state = run_stage(ctx, repo.id, "resolver",
                      [_entry("dec", "decision", "cents",
                              {"chosen": "largest remainder"}, "Decided largest remainder.")],
                      "decide")
    (action,) = state["proposed_actions"]
    assert action["action"] == "keep"
    assert action["downgraded_from"] == "supersede"
    assert state["merge_status"] == "clean"


def test_same_type_lifecycle_close_still_supersedes(session, repo):
    _seed(session, repo, [_entry("step", "next_step", "runbook",
                                 {"status": "open", "owner": "sam"}, "Write the runbook.")])
    ctx = _ctx(session, repo, {("close", "step"): "refines"})
    state = run_stage(ctx, repo.id, "closer",
                      [_entry("close", "next_step", "runbook",
                              {"status": "closed", "owner": "sam"}, "Runbook written.")],
                      "close")
    (action,) = state["proposed_actions"]
    assert action["action"] == "supersede"
    assert "downgraded_from" not in action


def test_cross_type_supersede_between_fact_types_untouched(session, repo):
    # the R06 pattern must keep working: state_change supersedes a stale finding
    _seed(session, repo, [_entry("f", "finding", "timeout",
                                 {"timeout_seconds": 60}, "Timeout is 60s.", origin="agent")])
    ctx = _ctx(session, repo, {("chg", "f"): "refines"})
    state = run_stage(ctx, repo.id, "changer",
                      [_entry("chg", "state_change", "timeout",
                              {"timeout_seconds": 30, "what_changed": "60 -> 30"},
                              "Changed timeout from 60s to 30s after load test.")],
                      "change")
    (action,) = state["proposed_actions"]
    assert action["action"] == "supersede"
    assert "downgraded_from" not in action


def test_two_supersedes_of_one_target_fail_closed_to_review(session, repo):
    _seed(session, repo, [_entry("f", "finding", "sizing",
                                 {"fpr": "0.1%"}, "Bloom FPR target is 0.1%.", origin="agent")])
    script = {("upd1", "f"): "refines", ("upd2", "f"): "subsumes"}
    ctx = _ctx(session, repo, script)
    state = run_stage(ctx, repo.id, "pusher",
                      [_entry("upd1", "finding", "sizing", {"fpr": "0.1%", "keys": "50M"},
                              "0.1% FPR at 50M keys.", origin="agent"),
                       _entry("upd2", "finding", "sizing", {"fpr": "0.1%", "mem": "180MB"},
                              "0.1% FPR, ~180MB memory.", origin="agent")],
                      "double update")
    actions = {a["temp_id"]: a for a in state["proposed_actions"]}
    kinds = sorted(a["action"] for a in actions.values())
    assert kinds == ["conflict", "supersede"], kinds
    assert state["merge_status"] == "needs_review"
    ambiguous = [c for c in state["conflicts"] if c["relation"] == "ambiguous_supersede"]
    assert len(ambiguous) == 1
    rows = session.execute(select(Conflict).where(Conflict.repo_id == repo.id)).scalars().all()
    assert any(c.relation == "ambiguous_supersede" and c.status == "open" for c in rows)

    # resolving the ambiguous extra as keep_existing (discard) lets the commit proceed
    amb_row = next(c for c in rows if c.relation == "ambiguous_supersede")
    cstate = run_commit(_ctx(session, repo, script), uuid.UUID(state["staging_id"]),
                        {str(amb_row.id): {"action": "keep_existing"}})
    assert cstate["merge_status"] == "committed", cstate.get("error")


def test_contradicts_conflict_has_no_default_winner(session, repo):
    _seed(session, repo, [_entry("f60", "finding", "timeout",
                                 {"timeout_seconds": 60}, "Timeout is 60s.", origin="agent")])
    ctx = _ctx(session, repo, {("f30", "f60"): "contradicts"})
    state = run_stage(ctx, repo.id, "asserter",
                      [_entry("f30", "finding", "timeout",
                              {"timeout_seconds": 30}, "Timeout is 30s.", origin="agent")],
                      "stale assert")
    assert state["merge_status"] == "needs_review"
    row = session.execute(select(Conflict).where(Conflict.repo_id == repo.id)).scalars().one()
    proposal = {k: v for k, v in (row.proposed_resolution or {}).items() if k != "rationale"}
    assert proposal == {}, proposal  # DF-3: no machine-proposed winner


def test_commit_backstop_rejects_double_supersede(session, repo):
    cstate = _seed(session, repo, [_entry("f", "finding", "x", {"v": 1}, "v is 1.", origin="agent")])
    from ctxvcs.dag.trees import master_tree

    target_id = str(next(iter(master_tree(session, repo.id))))
    from ctxvcs.core.canonical import content_hash
    from ctxvcs.core.entry import normalize_payload

    def mk(key, v):
        norm = normalize_payload(_entry(key, "finding", "x", {"v": v}, f"v is {v}.", origin="agent"))
        return {**norm, "id": str(uuid.uuid4()),
                "content_hash": content_hash(norm["type"], norm["fields"], norm["body"])}

    e1, e2 = mk("a", 2), mk("b", 3)
    forged = StagedEntries(
        id=uuid.uuid4(), repo_id=repo.id, author="forger",
        parent_commit=cstate["commit_hash"], entries=[e1, e2],
        proposed_actions=[
            {"temp_id": e1["id"], "action": "supersede", "target_entry_id": target_id},
            {"temp_id": e2["id"], "action": "supersede", "target_entry_id": target_id},
        ],
        session_summary="forged double supersede", status="pending",
    )
    session.add(forged)
    session.flush()
    try:
        commit_staged(session, forged)
        raise AssertionError("expected CommitError for double supersede")
    except CommitError as e:
        assert "two supersedes" in str(e)
