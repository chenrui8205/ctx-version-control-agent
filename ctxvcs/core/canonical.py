"""Canonical serialization + content hashing (§4.1).

content_hash = sha256(canonicalize(type, fields, body)) — sorted keys, normalized
whitespace; excludes provenance and embedding. `subject` is a shared field on every
entry type (§3), so it is part of `fields` and therefore part of the hash.
"""

import hashlib
import json
import re

_WS = re.compile(r"\s+")


def norm_ws(s: str) -> str:
    """Collapse whitespace runs and trim. Reflowed-but-identical text hashes identically."""
    return _WS.sub(" ", s).strip()


def normalize_subject_key(subject: str) -> str:
    """x-subject-key normalization: lower + trimmed (§4.1)."""
    return norm_ws(subject).lower()


def _canon_value(v):
    if isinstance(v, str):
        return norm_ws(v)
    if isinstance(v, dict):
        return {k: _canon_value(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_canon_value(x) for x in v]
    return v


def canonicalize(type_: str, fields: dict, body: str) -> str:
    payload = {"type": type_, "fields": _canon_value(fields), "body": norm_ws(body)}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(type_: str, fields: dict, body: str) -> str:
    return hashlib.sha256(canonicalize(type_, fields, body).encode("utf-8")).hexdigest()
