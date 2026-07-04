"""Deterministic field-collision prefilter (§6). No LLM, no NLP — a dict diff.

Same subject_key + same structured field name + different scalar value. A collision
does NOT auto-classify ("changed timeout from 60 to 30" refines; "timeout is 30" vs
"timeout is 60" contradicts — identical field diff). It FORCES constrained LLM
adjudication over {refines, subsumes, contradicts} with conflicting_fields pre-filled.
Scoped per subject (R20: near-identical wording across services must not collide).
Lifecycle/metadata fields declared x-collision-exempt on either side's type (status,
confidence, what_changed…) never collide — they describe the entry, not the subject.
"""

_SCALAR = (str, int, float, bool)


def collision_exempt_fields(entry_types: dict, *types: str) -> frozenset[str]:
    out: set[str] = set()
    for t in types:
        out.update(entry_types.get(t, {}).get("x-collision-exempt", []))
    return frozenset(out)


def field_collisions(
    existing_subject_key: str,
    existing_fields: dict,
    incoming_subject_key: str,
    incoming_fields: dict,
    exempt: frozenset[str] = frozenset(),
) -> list[str]:
    if existing_subject_key != incoming_subject_key:
        return []
    out: list[str] = []
    for name in sorted(set(existing_fields) & set(incoming_fields)):
        if name == "subject" or name in exempt:
            continue
        a, b = existing_fields[name], incoming_fields[name]
        if isinstance(a, _SCALAR) and isinstance(b, _SCALAR) and a != b:
            out.append(name)
    return out
