"""M1 standalone push (§8): raw notes → server-side extract node → normal pipeline."""

import uuid

from ctxvcs.config import settings
from ctxvcs.llm.fakes import FakeEmbedder, FakeExtractClient, ScriptedReconcileClient
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.repo_ops import current_schema

NOTES = """
friday notes — finished the runbook, opened one question.

```json
{"entries": [
   {"type": "finding", "subject": "replay-ordering", "fields": {"confidence": "high"},
    "body": "Replayed messages append to the topic tail; consumers may see them after newer events.",
    "provenance": {"origin": "human", "ts": "2026-07-05"}},
   {"type": "open_question", "subject": "idempotency-keys", "fields": {"status": "open", "blocking": false},
    "body": "Do we need idempotency keys before enabling auto-replay?",
    "provenance": {"origin": "human", "ts": "2026-07-05"}}
 ],
 "session_summary": "Runbook session: replay-ordering finding, idempotency question opened."}
```
"""


def _ctx(session, repo):
    return PipelineContext(
        session=session,
        embedder=FakeEmbedder(settings().embed_dim),
        reconciler=ScriptedReconcileClient({}),
        extractor=FakeExtractClient(),
        entry_types=current_schema(session, repo.id).entry_types,
    )


def test_raw_notes_stage_extracts_validates_and_commits(session, repo):
    state = run_stage(_ctx(session, repo), repo.id, "sam", [], "", raw_notes=NOTES)
    assert state.get("error") is None
    assert state["merge_status"] == "clean"
    assert len(state["proposed_actions"]) == 2
    assert all(a["action"] == "new" for a in state["proposed_actions"])
    # extractor's session_summary adopted when the pusher supplied none
    assert "Runbook session" in state["session_summary"]

    cstate = run_commit(_ctx(session, repo), uuid.UUID(state["staging_id"]))
    assert cstate["merge_status"] == "committed"


def test_raw_notes_extraction_failure_is_terminal(session, repo):
    state = run_stage(_ctx(session, repo), repo.id, "sam", [], "", raw_notes="no json block here")
    assert state["merge_status"] == "error"
    assert state["error"]["kind"] == "extraction"


def test_oversized_notes_rejected(session, repo):
    big = "x" * (settings().raw_notes_max_chars + 1)
    state = run_stage(_ctx(session, repo), repo.id, "sam", [], "", raw_notes=big)
    assert state["merge_status"] == "error"
    assert "exceed" in state["error"]["detail"]
