"""Write pipeline (§5): validate → embed → reconcile_vs_master → apply_actions → router.

mode='stage'  — dry-run: classify, simulate into proposed_actions, persist the staging
                row (+ Merge Request when contradicts found). Writes nothing to master.
mode='commit' — finalize: execute the recorded actions via the §4.3 transaction.
"""

import uuid
from dataclasses import dataclass, field
from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import text
from sqlalchemy.orm import Session

from ctxvcs.config import Settings, settings
from ctxvcs.core.entry import Entry, ValidationError, embed_text, validate_entries
from ctxvcs.dag.trees import entry_history, head_commit
from ctxvcs.embed import Embedder
from ctxvcs.llm.reconcile import reconcile_pair
from ctxvcs.llm.types import ACTION_FOR_RELATION, ReconcileClient, entry_view
from ctxvcs.store.commit_txn import (
    CommitError,
    ConflictsUnresolvedError,
    StaleParentError,
    commit_staged,
)
from ctxvcs.store.models import Conflict, MergeRequest, StagedEntries

# When one incoming entry relates to several master candidates, the most
# consequential relation governs its action: a detected contradiction must reach a
# human even if the entry also duplicates something else.
RELATION_PRECEDENCE = ["contradicts", "duplicate", "subsumed_by", "subsumes", "refines", "complementary", "unrelated"]


class PipelineState(TypedDict, total=False):
    repo_id: str
    parent_commit: str | None
    mode: str  # 'stage' | 'commit'
    author: str
    session_summary: str
    raw_entries: list[dict]
    incoming_entries: list[dict]
    proposed_actions: list[dict]
    conflicts: list[dict]
    merge_status: str  # clean | needs_review | committed | error
    staging_id: str
    merge_request_id: str | None
    commit_hash: str | None
    resolutions: dict
    error: dict | None
    _changed: list[str]  # entry_ids touched by a commit (compiler dirty set)


@dataclass
class PipelineContext:
    session: Session
    embedder: Embedder
    reconciler: ReconcileClient
    entry_types: dict
    cfg: Settings = field(default_factory=settings)
    # called after a successful commit txn: (commit_hash, changed_entry_ids)
    after_commit: Callable[[str, list[uuid.UUID]], None] = lambda *_: None


def _view(e: Entry | dict) -> dict:
    d = e.to_json() if isinstance(e, Entry) else e
    prov = d.get("provenance", {})
    v = entry_view(d["type"], d["fields"].get("subject", d["subject_key"]), d["fields"], d["body"],
                   prov.get("ts"), prov.get("origin"))
    if prov.get("fixture_key"):
        v["fixture_key"] = prov["fixture_key"]
    return v


def _candidates(ctx: PipelineContext, repo_id: str, entry: dict) -> list[dict]:
    """Retrieve-then-classify (§6): same subject_key OR embedding within 1 - TAU_CONF."""
    emb = entry.get("embedding")
    if emb:
        sql = """
            SELECT m.entry_id::text AS entry_id, e.content_hash, e.type, e.fields, e.body,
                   e.subject_key, e.provenance,
                   (e.embedding <=> CAST(:emb AS vector)) AS dist
            FROM master_entries m JOIN entries e ON e.content_hash = m.content_hash
            WHERE m.repo_id = :r
              AND (e.subject_key = :sk
                   OR (e.embedding <=> CAST(:emb AS vector)) < :maxdist)
            ORDER BY (e.subject_key = :sk) DESC, dist ASC NULLS LAST
            LIMIT :cap
            """
        params = {"r": repo_id, "sk": entry["subject_key"], "emb": str(emb),
                  "maxdist": 1.0 - ctx.cfg.tau_conf, "cap": ctx.cfg.reconcile_max_candidates}
    else:
        sql = """
            SELECT m.entry_id::text AS entry_id, e.content_hash, e.type, e.fields, e.body,
                   e.subject_key, e.provenance, NULL AS dist
            FROM master_entries m JOIN entries e ON e.content_hash = m.content_hash
            WHERE m.repo_id = :r AND e.subject_key = :sk
            LIMIT :cap
            """
        params = {"r": repo_id, "sk": entry["subject_key"], "cap": ctx.cfg.reconcile_max_candidates}
    rows = ctx.session.execute(text(sql), params).mappings()
    return [dict(r) for r in rows]


def build_pipeline(ctx: PipelineContext):
    def validate(state: PipelineState) -> PipelineState:
        try:
            entries = validate_entries(state["raw_entries"], ctx.entry_types)
        except ValidationError as ve:
            return {**state, "error": {"kind": "validation", "violations": ve.violations},
                    "merge_status": "error"}
        return {**state, "incoming_entries": [e.to_json() for e in entries]}

    def embed(state: PipelineState) -> PipelineState:
        entries = [Entry.from_json(d) for d in state["incoming_entries"]]
        vectors = ctx.embedder.embed([embed_text(e, ctx.entry_types) for e in entries])
        out = []
        for d, v in zip(state["incoming_entries"], vectors):
            out.append({**d, "embedding": v})
        return {**state, "incoming_entries": out}

    def reconcile(state: PipelineState) -> PipelineState:
        actions: list[dict] = []
        conflicts: list[dict] = []
        for inc in state["incoming_entries"]:
            cands = _candidates(ctx, state["repo_id"], inc)
            # exact content-hash match against master drops deterministically — no LLM
            exact = next((c for c in cands if c["content_hash"] == inc["content_hash"]), None)
            if exact is not None:
                actions.append({"temp_id": inc["id"], "relation": "duplicate", "action": "drop",
                                "target_entry_id": exact["entry_id"],
                                "target_content_hash": exact["content_hash"],
                                "confidence": 1.0, "rationale": "exact content-hash match",
                                "conflicting_fields": [], "path": "exact",
                                "subject_key": inc["subject_key"], "type": inc["type"]})
                continue
            outcomes = []
            for c in cands:
                po = reconcile_pair(
                    ctx.reconciler, _view(inc), _view({**c, "fields": c["fields"], "provenance": c["provenance"]}),
                    incoming_subject_key=inc["subject_key"],
                    existing_subject_key=c["subject_key"],
                    entry_types=ctx.entry_types,
                    cfg=ctx.cfg,
                )
                outcomes.append((po, c))
            governing = None
            for rel in RELATION_PRECEDENCE:
                hit = next(((po, c) for po, c in outcomes if po.result.relation == rel), None)
                if hit and rel != "unrelated":
                    governing = hit
                    break
            if governing is None:
                action = {"temp_id": inc["id"], "relation": "unrelated", "action": "new",
                          "target_entry_id": None, "target_content_hash": None,
                          "confidence": 1.0, "rationale": "no related master entry",
                          "conflicting_fields": [], "path": "llm",
                          "subject_key": inc["subject_key"], "type": inc["type"]}
            else:
                po, c = governing
                rel = po.result.relation
                action = {"temp_id": inc["id"], "relation": rel,
                          "action": ACTION_FOR_RELATION[rel],
                          "target_entry_id": c["entry_id"], "target_content_hash": c["content_hash"],
                          "confidence": po.result.confidence, "rationale": po.result.rationale,
                          "conflicting_fields": po.result.conflicting_fields, "path": po.path,
                          "subject_key": inc["subject_key"], "type": inc["type"]}
                if rel == "complementary":
                    action["action"] = "keep"  # M0: keep both (§6); merge_body is M1
                if rel == "contradicts":
                    conflicts.append({
                        "temp_id": inc["id"],
                        "subject_key": inc["subject_key"],
                        "existing_entry_id": c["entry_id"],
                        "existing_content_hash": c["content_hash"],
                        "existing_commit": _introducing_commit(ctx, state["repo_id"], c),
                        "relation": rel,
                        "confidence": po.result.confidence,
                        "conflicting_fields": po.result.conflicting_fields,
                        "rationale": po.result.rationale,
                        # proposal only — a human decides every contradicts on master (§ Core 8)
                        "proposed_resolution": {"action": "supersede", "winner": "incoming"},
                    })
            actions.append(action)
        return {**state, "proposed_actions": actions, "conflicts": conflicts}

    def apply_actions(state: PipelineState) -> PipelineState:
        if state["mode"] == "stage":
            staged = StagedEntries(
                id=uuid.UUID(state["staging_id"]),
                repo_id=uuid.UUID(state["repo_id"]),
                author=state.get("author"),
                parent_commit=state.get("parent_commit") or head_commit(
                    ctx.session, uuid.UUID(state["repo_id"])
                ),
                entries=[{**e, "provenance": {**e.get("provenance", {}),
                                              "session_id": state["staging_id"]}}
                         for e in state["incoming_entries"]],
                proposed_actions=state["proposed_actions"],
                session_summary=state.get("session_summary"),
                status="pending",
            )
            ctx.session.add(staged)
            ctx.session.flush()  # conflicts/MR FK-reference the staging row; no relationships mapped
            mr_id = None
            if state["conflicts"]:
                mr = MergeRequest(id=uuid.uuid4(), repo_id=staged.repo_id, staging_id=staged.id,
                                  origin="push", status="open")
                ctx.session.add(mr)
                ctx.session.flush()
                mr_id = str(mr.id)
                for cf in state["conflicts"]:
                    inc_json = next(e for e in staged.entries if e["id"] == cf["temp_id"])
                    ctx.session.add(Conflict(
                        id=uuid.uuid4(), repo_id=staged.repo_id, merge_request_id=mr.id,
                        subject_key=cf["subject_key"],
                        existing_content_hash=cf["existing_content_hash"],
                        incoming=inc_json,
                        existing_commit=cf["existing_commit"],
                        relation=cf["relation"], confidence=cf["confidence"],
                        conflicting_fields=cf["conflicting_fields"],
                        proposed_resolution={**cf["proposed_resolution"], "rationale": cf["rationale"]},
                        status="open",
                    ))
            ctx.session.commit()
            return {**state, "merge_request_id": mr_id}

        # mode == 'commit': §4.3 transaction
        staged = ctx.session.get(StagedEntries, uuid.UUID(state["staging_id"]))
        try:
            result = commit_staged(ctx.session, staged, state.get("resolutions") or {})
        except ConflictsUnresolvedError as e:
            return {**state, "merge_status": "needs_review", "merge_request_id": str(e.merge_request_id)}
        except (StaleParentError, CommitError) as e:
            return {**state, "merge_status": "error", "error": {"kind": type(e).__name__, "detail": str(e)}}
        return {**state, "merge_status": "committed", "commit_hash": result.commit_hash,
                "_changed": [str(x) for x in result.changed_entry_ids]}

    def router(state: PipelineState) -> PipelineState:
        if state.get("error"):
            return state
        if state["mode"] == "stage":
            status = "needs_review" if state["conflicts"] else "clean"
            return {**state, "merge_status": status}
        if state.get("commit_hash"):
            ctx.after_commit(state["commit_hash"], [uuid.UUID(x) for x in state.get("_changed", [])])
        return state

    g = StateGraph(PipelineState)
    g.add_node("validate", validate)
    g.add_node("embed", embed)
    g.add_node("reconcile", reconcile)
    g.add_node("apply_actions", apply_actions)
    g.add_node("router", router)
    g.set_conditional_entry_point(lambda s: "apply_actions" if s["mode"] == "commit" else "validate")
    g.add_conditional_edges("validate", lambda s: END if s.get("error") else "embed")
    g.add_edge("embed", "reconcile")
    g.add_edge("reconcile", "apply_actions")
    g.add_edge("apply_actions", "router")
    g.add_edge("router", END)
    return g.compile()


def _introducing_commit(ctx: PipelineContext, repo_id: str, candidate: dict) -> str | None:
    hist = entry_history(ctx.session, uuid.UUID(repo_id), uuid.UUID(candidate["entry_id"]))
    return next((v["commit"] for v in hist if v["content_hash"] == candidate["content_hash"]), None)


def run_stage(ctx: PipelineContext, repo_id: uuid.UUID, author: str, raw_entries: list[dict],
              session_summary: str, parent_commit: str | None = None) -> PipelineState:
    graph = build_pipeline(ctx)
    return graph.invoke({
        "repo_id": str(repo_id), "mode": "stage", "author": author,
        "raw_entries": raw_entries, "session_summary": session_summary,
        "parent_commit": parent_commit, "staging_id": str(uuid.uuid4()),
        "conflicts": [], "proposed_actions": [], "error": None,
    })


def run_commit(ctx: PipelineContext, staging_id: uuid.UUID, resolutions: dict | None = None) -> PipelineState:
    graph = build_pipeline(ctx)
    return graph.invoke({
        "repo_id": "", "mode": "commit", "staging_id": str(staging_id),
        "resolutions": resolutions or {}, "conflicts": [], "error": None,
    })
