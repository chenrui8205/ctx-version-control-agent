"""Claude reconcile client — structured tool output, strict JSON (§ Core: structured
outputs wherever the output is machine-consumed). Prompt is versioned code (§12.6.2)."""

import json
from functools import lru_cache
from pathlib import Path

import anthropic

from ctxvcs.config import settings
from ctxvcs.llm.types import CONSTRAINED_RELATIONS, RELATIONS, ReconcileResult

PROMPTS = Path(__file__).parent / "prompts"


@lru_cache
def reconcile_prompt() -> str:
    return (PROMPTS / "reconcile.md").read_text()


def _tool(constrained: bool) -> dict:
    allowed = list(CONSTRAINED_RELATIONS if constrained else RELATIONS)
    return {
        "name": "classify_relation",
        "description": "Report the relation between the incoming and existing entry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "relation": {"enum": allowed},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "rationale": {"type": "string"},
                "conflicting_fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["relation", "confidence", "rationale"],
        },
    }


class ClaudeReconcileClient:
    def __init__(self, client: anthropic.Anthropic | None = None):
        self._client = client or anthropic.Anthropic(max_retries=3)

    def classify(
        self,
        incoming: dict,
        existing: dict,
        *,
        constrained: bool = False,
        conflicting_fields: tuple[str, ...] = (),
    ) -> ReconcileResult:
        cfg = settings()
        payload: dict = {
            "existing": existing,
            "incoming": incoming,
        }
        if constrained:
            payload["field_collision"] = {
                "detected": True,
                "conflicting_fields": list(conflicting_fields),
                "instruction": "Constrained mode: relation must be refines, subsumes, or contradicts.",
            }
        msg = self._client.messages.create(
            model=cfg.reconcile_model,
            max_tokens=cfg.reconcile_max_tokens,
            system=reconcile_prompt(),
            tools=[_tool(constrained)],
            tool_choice={"type": "tool", "name": "classify_relation"},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        data = block.input
        relation = data.get("relation", "")
        if relation not in RELATIONS:
            # malformed output on the open path fails safe: keep both, flag low confidence
            return ReconcileResult(
                relation="complementary",
                confidence=0.0,
                rationale=f"malformed model relation {relation!r}; kept both",
                conflicting_fields=list(conflicting_fields),
            )
        return ReconcileResult(
            relation=relation,
            confidence=float(data.get("confidence", 0.0)),
            rationale=str(data.get("rationale", "")),
            conflicting_fields=list(data.get("conflicting_fields") or []),
        )
