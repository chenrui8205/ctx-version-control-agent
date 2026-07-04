"""Reconcile relation vocabulary, the action collapse (§12.2), and the client interface.

All LLM calls sit behind these interfaces with deterministic fakes (§14) — unit tests
never hit the real API.
"""

from dataclasses import dataclass, field
from typing import Protocol

RELATIONS = ("duplicate", "subsumed_by", "subsumes", "complementary", "refines", "contradicts", "unrelated")

# Collision path is constrained to these three (§6); anything else is overridden fail-closed.
CONSTRAINED_RELATIONS = ("refines", "subsumes", "contradicts")

# Relation → what M0 does (§6 routing table / §12.2 action collapse)
ACTION_FOR_RELATION = {
    "duplicate": "drop",
    "subsumed_by": "drop",
    "subsumes": "supersede",
    "refines": "supersede",
    "complementary": "keep",
    "unrelated": "keep",
    "contradicts": "conflict",
}


@dataclass
class ReconcileResult:
    relation: str
    confidence: float
    rationale: str = ""
    conflicting_fields: list[str] = field(default_factory=list)


class ReconcileClient(Protocol):
    def classify(
        self,
        incoming: dict,
        existing: dict,
        *,
        constrained: bool = False,
        conflicting_fields: tuple[str, ...] = (),
    ) -> ReconcileResult:
        """incoming/existing are entry views: {type, subject, fields, body, ts, origin}."""
        ...


def entry_view(type_: str, subject: str, fields: dict, body: str, ts: str | None, origin: str | None) -> dict:
    """The classifier's input shape — includes BOTH sides' provenance ts + origin (§6)."""
    return {"type": type_, "subject": subject, "fields": fields, "body": body, "ts": ts, "origin": origin}
