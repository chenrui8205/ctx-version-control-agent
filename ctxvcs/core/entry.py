"""Entry domain object (§4.1) and push-time validation (§3: JSON Schema, no LLM)."""

import uuid
from dataclasses import dataclass, field

import jsonschema

from ctxvcs.core.canonical import content_hash, normalize_subject_key
from ctxvcs.core.default_schema import STATUSFUL_TYPES


class ValidationError(Exception):
    def __init__(self, violations: list[dict]):
        self.violations = violations
        super().__init__(f"{len(violations)} entry validation failure(s)")


@dataclass
class Entry:
    """Unit of versioning. `id` is transient until committed, then permanent (§ Core 9)."""

    type: str
    fields: dict  # includes `subject` (shared field, §3)
    body: str
    provenance: dict  # {author, session_id, ts, origin: human|agent, note}
    access_labels: list[str] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    embedding: list[float] | None = None

    @property
    def subject_key(self) -> str:
        return normalize_subject_key(str(self.fields.get("subject", "")))

    @property
    def content_hash(self) -> str:
        return content_hash(self.type, self.fields, self.body)

    def to_json(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.type,
            "fields": self.fields,
            "body": self.body,
            "subject_key": self.subject_key,
            "content_hash": self.content_hash,
            "access_labels": self.access_labels,
            "provenance": self.provenance,
            "embedding": self.embedding,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Entry":
        return cls(
            id=uuid.UUID(d["id"]),
            type=d["type"],
            fields=d["fields"],
            body=d["body"],
            provenance=d.get("provenance", {}),
            access_labels=d.get("access_labels", []),
            embedding=d.get("embedding"),
        )


def normalize_payload(raw: dict) -> dict:
    """Fold a top-level `subject` into fields (API/fixture ergonomics) and fill
    status defaults for lifecycle types."""
    fields = dict(raw.get("fields") or {})
    if "subject" in raw and "subject" not in fields:
        fields["subject"] = raw["subject"]
    if raw["type"] in STATUSFUL_TYPES and "status" not in fields:
        fields["status"] = "open"
    return {**raw, "fields": fields}


def validate_entries(raw_entries: list[dict], entry_types: dict) -> list[Entry]:
    """JSON Schema per entry; hard failure ⇒ ValidationError with violations (⇒ 422)."""
    out: list[Entry] = []
    violations: list[dict] = []
    for i, raw in enumerate(raw_entries):
        etype = raw.get("type")
        if etype not in entry_types:
            violations.append({"index": i, "error": f"unknown entry type {etype!r}"})
            continue
        norm = normalize_payload(raw)
        schema = entry_types[etype]["schema"]
        validator = jsonschema.Draft202012Validator(schema)
        errs = [e.message for e in validator.iter_errors(norm["fields"])]
        if not isinstance(norm.get("body"), str) or not norm["body"].strip():
            errs.append("body must be a non-empty string")
        if errs:
            violations.append({"index": i, "type": etype, "errors": errs})
            continue
        prov = dict(norm.get("provenance") or {})
        prov.setdefault("origin", "agent")
        entry = Entry(
            type=etype,
            fields=norm["fields"],
            body=norm["body"],
            provenance=prov,
            access_labels=list(norm.get("access_labels") or entry_types[etype].get("x-access-default", [])),
        )
        out.append(entry)
    if violations:
        raise ValidationError(violations)
    # exact content-hash duplicates within the batch collapse for free (§5.1)
    seen: dict[str, Entry] = {}
    deduped: list[Entry] = []
    for e in out:
        if e.content_hash in seen:
            continue
        seen[e.content_hash] = e
        deduped.append(e)
    return deduped


def embed_text(entry: Entry, entry_types: dict) -> str:
    """Deterministic embedding input per x-embed-fields + body."""
    spec = entry_types.get(entry.type, {})
    parts = [entry.type]
    for f in spec.get("x-embed-fields", ["subject"]):
        v = entry.fields.get(f)
        if v is not None:
            parts.append(f"{f}: {v}")
    parts.append(entry.body)
    return "\n".join(parts)
