"""Invariant: content-hash canonicalization stability (§14)."""

from ctxvcs.core.canonical import canonicalize, content_hash, normalize_subject_key
from ctxvcs.core.entry import Entry


def test_key_order_irrelevant():
    a = content_hash("finding", {"subject": "x", "a": 1, "b": 2}, "body")
    b = content_hash("finding", {"b": 2, "a": 1, "subject": "x"}, "body")
    assert a == b


def test_whitespace_normalized():
    a = content_hash("finding", {"subject": "x"}, "the  quick\n brown   fox")
    b = content_hash("finding", {"subject": "x"}, "the quick brown fox")
    assert a == b


def test_subject_changes_hash():
    a = content_hash("finding", {"subject": "svc-a", "t": 60}, "timeout is 60")
    b = content_hash("finding", {"subject": "svc-b", "t": 60}, "timeout is 60")
    assert a != b


def test_provenance_and_embedding_excluded():
    e1 = Entry(type="finding", fields={"subject": "x"}, body="b",
               provenance={"author": "alice", "ts": "2026-01-01"}, embedding=[0.1] * 4)
    e2 = Entry(type="finding", fields={"subject": "x"}, body="b",
               provenance={"author": "bob", "ts": "2026-06-06"}, embedding=None)
    assert e1.content_hash == e2.content_hash


def test_canonicalize_deterministic_bytes():
    s1 = canonicalize("decision", {"subject": "S", "chosen": "Redis "}, " use  redis ")
    s2 = canonicalize("decision", {"chosen": "Redis", "subject": "S"}, "use redis")
    assert s1 == s2


def test_subject_key_normalization():
    assert normalize_subject_key("  Ban-Service  Consumer ") == "ban-service consumer"
