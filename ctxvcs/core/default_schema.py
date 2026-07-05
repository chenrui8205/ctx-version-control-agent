"""The working-context starter pack (§3): built-in entry types, seeded into
schema_versions v1 on repo creation. POST /schema can extend/override.

Every type shares: `subject` (string, x-subject-key), optional structured fields,
freeform `body`, and provenance {author, session_id, ts, origin, note}.
Schemas are open (additionalProperties: true) — sessions attach ad-hoc structured
fields (e.g. `consumer_timeout_seconds`) and the field-collision prefilter (§6)
works over whatever is present.
"""

_COMMON_REQUIRED = ["subject"]


def _t(
    properties: dict,
    *,
    required: list[str] | None = None,
    embed: list[str] | None = None,
    collision_exempt: list[str] | None = None,
    lifecycle: bool = False,
) -> dict:
    props = {"subject": {"type": "string", "minLength": 1}, **properties}
    return {
        "x-subject-key": "subject",
        "x-access-default": [],  # recorded M0, enforced M2
        "x-embed-fields": embed or ["subject"],
        # lifecycle/metadata fields, not fact claims: exempt from the §6 collision
        # prefilter (confidence revisions, status closes, event descriptions are the
        # normal session pattern — seed fixtures R07/R08/R12/R13/R15 pin this down)
        "x-collision-exempt": collision_exempt or [],
        # open/closable work items: only their own type may supersede them
        # (§6 routing rule 1; dogfood fixtures R22-R25 pin this down)
        "x-lifecycle": lifecycle,
        "schema": {
            "type": "object",
            "properties": props,
            "required": _COMMON_REQUIRED + (required or []),
            "additionalProperties": True,
        },
    }


DEFAULT_ENTRY_TYPES: dict[str, dict] = {
    "decision": _t(
        {
            "chosen": {"type": "string"},
            "alternatives": {"type": "array", "items": {"type": "string"}},
        },
        embed=["subject", "chosen"],
    ),
    "finding": _t(
        {
            "sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"enum": ["low", "med", "high"]},
        },
        embed=["subject"],
        collision_exempt=["confidence", "sources"],
    ),
    "state_change": _t(
        {
            "what_changed": {"type": "string"},
            "where": {"type": "string"},
        },
        embed=["subject", "what_changed", "where"],
        collision_exempt=["what_changed", "where"],
    ),
    "open_question": _t(
        {
            "status": {"enum": ["open", "closed"]},
            "blocking": {"type": "boolean"},
        },
        required=["status"],
        embed=["subject"],
        collision_exempt=["status", "blocking"],
        lifecycle=True,
    ),
    "next_step": _t(
        {
            "status": {"enum": ["open", "closed"]},
            "owner": {"type": "string"},
        },
        required=["status"],
        embed=["subject"],
        collision_exempt=["status", "owner"],
        lifecycle=True,
    ),
    "constraint": _t(
        {
            "kind": {"enum": ["technical", "legal", "product"]},
            "hard": {"type": "boolean"},
        },
        embed=["subject", "kind"],
    ),
}

# Types whose `status` field defaults to "open" when the client omits it.
STATUSFUL_TYPES = {"open_question", "next_step"}
