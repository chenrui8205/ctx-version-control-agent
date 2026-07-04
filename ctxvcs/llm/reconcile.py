"""reconcile_vs_master pair adjudication (§6) — the ONE relation classifier.

Wraps any ReconcileClient with the deterministic policy that is not the model's job:
- field-collision prefilter decides the path (collision ⇒ constrained adjudication)
- fail-closed: a collided pair returning anything outside {refines, subsumes,
  contradicts} is overridden to contradicts
- low-confidence contradicts on the OPEN path is downgraded per config (collision-path
  contradicts is never downgraded — that would reopen the silent-corruption hole)
"""

from dataclasses import dataclass

from ctxvcs.config import Settings, settings
from ctxvcs.core.default_schema import DEFAULT_ENTRY_TYPES
from ctxvcs.core.prefilter import collision_exempt_fields, field_collisions
from ctxvcs.llm.types import CONSTRAINED_RELATIONS, ReconcileClient, ReconcileResult


@dataclass
class PairOutcome:
    result: ReconcileResult
    path: str  # 'collision' | 'llm'
    overridden_from: str | None = None  # fail-closed audit trail
    downgraded_from: str | None = None


def reconcile_pair(
    client: ReconcileClient,
    incoming: dict,
    existing: dict,
    *,
    incoming_subject_key: str,
    existing_subject_key: str,
    entry_types: dict | None = None,
    cfg: Settings | None = None,
) -> PairOutcome:
    cfg = cfg or settings()
    entry_types = entry_types or DEFAULT_ENTRY_TYPES
    exempt = collision_exempt_fields(entry_types, incoming.get("type", ""), existing.get("type", ""))
    collisions = field_collisions(
        existing_subject_key,
        existing.get("fields", {}),
        incoming_subject_key,
        incoming.get("fields", {}),
        exempt=exempt,
    )
    constrained = bool(collisions)

    result = client.classify(
        incoming, existing, constrained=constrained, conflicting_fields=tuple(collisions)
    )

    overridden_from = None
    downgraded_from = None
    if constrained:
        # pre-filled conflicting_fields always survive
        merged = list(dict.fromkeys([*collisions, *result.conflicting_fields]))
        result.conflicting_fields = merged
        if result.relation not in CONSTRAINED_RELATIONS:
            overridden_from = result.relation
            result = ReconcileResult(
                relation="contradicts",
                confidence=result.confidence,
                rationale=f"fail-closed override (model said {result.relation!r}): {result.rationale}",
                conflicting_fields=merged,
            )
    elif result.relation == "contradicts" and result.confidence < cfg.conf_min:
        downgraded_from = "contradicts"
        result = ReconcileResult(
            relation=cfg.low_conf_contradicts_downgrade,
            confidence=result.confidence,
            rationale=f"downgraded from contradicts (confidence {result.confidence:.2f} "
            f"< CONF_MIN {cfg.conf_min}): {result.rationale}",
            conflicting_fields=result.conflicting_fields,
        )

    return PairOutcome(
        result=result,
        path="collision" if constrained else "llm",
        overridden_from=overridden_from,
        downgraded_from=downgraded_from,
    )
