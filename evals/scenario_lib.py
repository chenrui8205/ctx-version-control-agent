"""Golden scenario library (§12.3) — S1/S2 assert END-STATE, not just outputs.

Shared by ctxvcs/tests/test_scenarios.py (fake mode, CI) and evals/run_scenarios.py
(fake + live). Fake mode scripts relations by fixture key and exercises pipeline,
transaction, and compiler logic independent of model quality.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.compiler.build import compile_pages, serve_page
from ctxvcs.config import settings
from ctxvcs.dag.trees import commit_tree, entry_history, head_commit, master_tree
from ctxvcs.llm.fakes import FakeEmbedder, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.models import Conflict, EntryRow, MergeRequest, WikiPage
from ctxvcs.store.repo_ops import create_repo, current_schema

SCENARIOS = Path(__file__).resolve().parent / "fixtures" / "scenarios"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ScenarioRun:
    name: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = ""):
        self.checks.append(Check(name, bool(ok), detail))

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)


def load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS / f"{name}.json").read_text())


def raw_entry(spec: dict, nonce: str) -> dict:
    """Fixture entry -> stage payload. Bodies get a run nonce so repeated runs
    against a shared database stay content-isolated."""
    return {
        "type": spec["type"],
        "subject": spec["subject"],
        "fields": spec.get("fields", {}),
        "body": spec["body"] + f" [run {nonce}]",
        "provenance": {"ts": spec.get("ts"), "origin": spec.get("origin", "agent"),
                       "fixture_key": spec["key"]},
    }


def make_ctx(session: Session, repo_id: uuid.UUID, scenario: dict, mode: str) -> PipelineContext:
    if mode == "fake":
        script = {(s["incoming"], s["existing"]): s["relation"] for s in scenario.get("script", [])}
        reconciler = ScriptedReconcileClient(script)
        embedder = FakeEmbedder(settings().embed_dim)
    else:
        from ctxvcs.embed import get_embedder
        from ctxvcs.llm.claude import ClaudeReconcileClient

        reconciler = ClaudeReconcileClient()
        embedder = get_embedder()
    return PipelineContext(
        session=session,
        embedder=embedder,
        reconciler=reconciler,
        entry_types=current_schema(session, repo_id).entry_types,
        after_commit=lambda _h, changed: compile_pages(session, repo_id, changed),
    )


def _key_by_temp(staged_entries: list[dict]) -> dict[str, str]:
    return {e["id"]: (e.get("provenance") or {}).get("fixture_key") for e in staged_entries}


def seed_commit(session: Session, repo_id: uuid.UUID, scenario: dict, nonce: str, mode: str) -> str:
    ctx = make_ctx(session, repo_id, scenario, mode)
    state = run_stage(ctx, repo_id, "seeder",
                      [raw_entry(s, nonce) for s in scenario["seed"]],
                      scenario.get("seed_summary", "seed"))
    assert state["merge_status"] == "clean", f"seed stage not clean: {state.get('error')}"
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed", f"seed commit failed: {cstate.get('error')}"
    return cstate["commit_hash"]


def page_snapshot(session: Session, repo_id: uuid.UUID) -> dict[str, tuple[str, str]]:
    rows = session.execute(select(WikiPage).where(WikiPage.repo_id == repo_id)).scalars()
    return {p.slug: (p.input_hash, p.content) for p in rows}


def run_s1(session: Session, mode: str = "fake") -> ScenarioRun:
    sc = load_scenario("s1")
    r = ScenarioRun(sc["name"])
    nonce = uuid.uuid4().hex[:8]
    repo, _tok = create_repo(session, f"s1-{nonce}", "eval")
    session.commit()
    compile_pages(session, repo.id, None)

    seed_commit(session, repo.id, sc, nonce, mode)
    tree0 = master_tree(session, repo.id)
    r.add("C0 seeded with four entries", len(tree0) == 4, f"{len(tree0)} entries")
    pages0 = page_snapshot(session, repo.id)

    # ---- stage the mixed second session
    ctx = make_ctx(session, repo.id, sc, mode)
    state = run_stage(ctx, repo.id, "pusher",
                      [raw_entry(s, nonce) for s in sc["push"]], sc.get("push_summary", "push"))
    keys = _key_by_temp(state["incoming_entries"])
    got_actions = {keys[a["temp_id"]]: a["action"] for a in state["proposed_actions"]}
    r.add("preview actions exactly {drop, supersede, conflict, new, new}",
          got_actions == sc["expected_actions"], json.dumps(got_actions, sort_keys=True))
    r.add("stage leaves master unmoved", master_tree(session, repo.id) == tree0)
    r.add("router says needs_review", state["merge_status"] == "needs_review")

    mrs = session.execute(select(MergeRequest).where(MergeRequest.repo_id == repo.id)).scalars().all()
    r.add("exactly one MR", len(mrs) == 1)
    conflicts = session.execute(
        select(Conflict).where(Conflict.merge_request_id == mrs[0].id)
    ).scalars().all() if mrs else []
    r.add("one conflict carrying conflicting_fields",
          len(conflicts) == 1 and conflicts[0].conflicting_fields == sc["expected_conflicting_fields"]["p-conflict"],
          str([c.conflicting_fields for c in conflicts]))

    # ---- resolve keep-incoming and commit
    resolutions = {str(conflicts[0].id): {"action": "keep_incoming"}} if conflicts else {}
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]), resolutions)
    r.add("resolution commit succeeds", cstate["merge_status"] == "committed", str(cstate.get("error")))

    tree1 = master_tree(session, repo.id)
    head = head_commit(session, repo.id)
    r.add("master_entries ≡ HEAD tree", tree1 == commit_tree(session, head))
    r.add("HEAD tree has exactly 6 entries", len(tree1) == 6, f"{len(tree1)}")

    by_key_seed = _entries_by_key(session, sc["seed"], nonce)
    by_key_push = _entries_by_key(session, sc["push"], nonce)
    timeout_id = _tree_id_for(tree0, by_key_seed["seed-timeout"])
    decision_id = _tree_id_for(tree0, by_key_seed["seed-decision"])
    r.add("superseded timeout keeps its entry_id",
          tree1.get(timeout_id) == by_key_push["p-refine"], str(timeout_id))
    r.add("conflict winner adopts existing decision entry_id",
          tree1.get(decision_id) == by_key_push["p-conflict"])
    r.add("constraint and next_step untouched",
          tree1.get(_tree_id_for(tree0, by_key_seed["seed-rocketmq"])) == by_key_seed["seed-rocketmq"]
          and tree1.get(_tree_id_for(tree0, by_key_seed["seed-step"])) == by_key_seed["seed-step"])

    old_row = session.get(EntryRow, by_key_seed["seed-timeout"])
    session.refresh(old_row)
    r.add("old version marked superseded_by in provenance",
          (old_row.provenance or {}).get("superseded_by", {}).get("content_hash") == by_key_push["p-refine"])

    # ---- compiler: exactly the dirty pages recompiled
    pages1 = page_snapshot(session, repo.id)
    changed_slugs = {s for s in pages1 if s not in pages0 or pages1[s][0] != pages0[s][0]
                     or pages1[s][1] != pages0[s][1]}
    expected_changed = {"ban-service-consumer", "reconcile-candidate-retrieval",
                        "ban-negative-cache", "saga-compensation",
                        "open-threads", "journal", "index"}
    r.add("recompiled exactly touched subjects + open-threads + journal + index",
          changed_slugs == expected_changed, str(sorted(changed_slugs)))
    r.add("untouched subject pages keep input_hash",
          pages1["rocketmq-delivery"][0] == pages0["rocketmq-delivery"][0]
          and pages1["dlq-replay-runbook"][0] == pages0["dlq-replay-runbook"][0])

    journal = serve_page(session, repo.id, "journal")["content"]
    newest_block = journal.split("## ")[1] if "## " in journal else ""
    r.add("journal newest session block lists the decision conflict as resolved",
          "Resolved conflicts" in newest_block and "reconcile-candidate-retrieval" in newest_block
          and "keep_incoming" in newest_block)
    facts = serve_page(session, repo.id, "ban-service-consumer")["content"]
    r.add("subject Facts row shows the new timeout", "| consumer_timeout_seconds | 30 |" in facts)
    return r


def run_s2(session: Session, mode: str = "fake") -> ScenarioRun:
    sc = load_scenario("s2")
    r = ScenarioRun(sc["name"])
    nonce = uuid.uuid4().hex[:8]
    repo, _tok = create_repo(session, f"s2-{nonce}", "eval")
    session.commit()
    compile_pages(session, repo.id, None)

    seed_commit(session, repo.id, sc, nonce, mode)
    tree0 = master_tree(session, repo.id)
    by_key_seed = _entries_by_key(session, sc["seed"], nonce)
    step_id = _tree_id_for(tree0, by_key_seed["seed-step"])

    ot0 = serve_page(session, repo.id, "open-threads")["content"]
    r.add("open-threads lists the open step before the push",
          "Write the DLQ replay runbook" in ot0)

    ctx = make_ctx(session, repo.id, sc, mode)
    state = run_stage(ctx, repo.id, "closer",
                      [raw_entry(s, nonce) for s in sc["push"]], sc.get("push_summary", "push"))
    keys = _key_by_temp(state["incoming_entries"])
    got = {keys[a["temp_id"]]: a["action"] for a in state["proposed_actions"]}
    r.add("close is a refines push (supersede) + new question kept",
          got == sc["expected_actions"], json.dumps(got, sort_keys=True))
    r.add("clean session — no MR", state["merge_status"] == "clean")
    cstate = run_commit(ctx, uuid.UUID(state["staging_id"]))
    r.add("commit succeeds", cstate["merge_status"] == "committed", str(cstate.get("error")))

    ot = serve_page(session, repo.id, "open-threads")["content"]
    r.add("open-threads no longer lists the step", "Write the DLQ replay runbook" not in ot)
    r.add("open-threads lists the new question", "thundering herd" in ot)

    journal = serve_page(session, repo.id, "journal")["content"]
    newest_block = journal.split("## ")[1] if "## " in journal else ""
    r.add("journal newest block shows the step under Closed",
          "**Closed**" in newest_block and "runbook written" in newest_block)

    hist = entry_history(session, repo.id, step_id)
    r.add("entry history returns the two-version chain", len(hist) == 2,
          str([h["content_hash"][:8] for h in hist]))
    return r


def _entries_by_key(session: Session, specs: list[dict], nonce: str) -> dict[str, str]:
    """fixture key -> content_hash (recomputed the same way the pipeline does)."""
    from ctxvcs.core.canonical import content_hash
    from ctxvcs.core.entry import normalize_payload

    out = {}
    for s in specs:
        norm = normalize_payload(raw_entry(s, nonce))
        out[s["key"]] = content_hash(norm["type"], norm["fields"], norm["body"])
    return out


def _tree_id_for(tree: dict, content_hash: str) -> uuid.UUID | None:
    return next((k for k, v in tree.items() if v == content_hash), None)
