"""§6 prefilter dict-diff + fail-closed/downgrade policy — deterministic, no fixtures."""

from ctxvcs.core.default_schema import DEFAULT_ENTRY_TYPES
from ctxvcs.core.prefilter import collision_exempt_fields, field_collisions
from ctxvcs.llm.reconcile import reconcile_pair
from ctxvcs.llm.types import ReconcileResult


def test_collision_fires_on_scalar_diff_same_subject():
    cols = field_collisions("s", {"consumer_timeout_seconds": 60}, "s", {"consumer_timeout_seconds": 30})
    assert cols == ["consumer_timeout_seconds"]


def test_collision_scoped_per_subject_r20():
    cols = field_collisions("ban-service-consumer", {"consumer_timeout_seconds": 60},
                            "checkout-service-consumer", {"consumer_timeout_seconds": 45})
    assert cols == []


def test_collision_ignores_equal_values_and_nonscalars():
    cols = field_collisions("s", {"chosen": "Redis", "alternatives": ["a"]},
                            "s", {"chosen": "Redis", "alternatives": ["b"]})
    assert cols == []


def test_lifecycle_fields_exempt():
    exempt = collision_exempt_fields(DEFAULT_ENTRY_TYPES, "next_step", "next_step")
    cols = field_collisions("s", {"status": "open", "owner": "a"}, "s",
                            {"status": "closed", "owner": "b"}, exempt=exempt)
    assert cols == []
    exempt = collision_exempt_fields(DEFAULT_ENTRY_TYPES, "finding", "finding")
    assert field_collisions("s", {"confidence": "high"}, "s", {"confidence": "med"}, exempt=exempt) == []


class _Stub:
    def __init__(self, relation, confidence=0.9):
        self.r, self.c = relation, confidence

    def classify(self, incoming, existing, *, constrained=False, conflicting_fields=()):
        return ReconcileResult(self.r, self.c, "stub", list(conflicting_fields))


def _pair(rel, conf, existing_fields, incoming_fields, subject="s"):
    return reconcile_pair(
        _Stub(rel, conf),
        {"type": "finding", "fields": incoming_fields, "body": "b"},
        {"type": "finding", "fields": existing_fields, "body": "b"},
        incoming_subject_key=subject, existing_subject_key=subject,
    )


def test_fail_closed_override_on_collision():
    out = _pair("duplicate", 0.9, {"t": 60}, {"t": 30})
    assert out.path == "collision"
    assert out.result.relation == "contradicts"
    assert out.overridden_from == "duplicate"
    assert out.result.conflicting_fields == ["t"]


def test_collision_allows_refines_through():
    out = _pair("refines", 0.9, {"t": 60}, {"t": 30})
    assert out.result.relation == "refines"
    assert out.overridden_from is None


def test_low_confidence_contradicts_downgraded_on_open_path_only():
    out = _pair("contradicts", 0.3, {}, {})
    assert out.path == "llm"
    assert out.result.relation == "complementary"  # config default downgrade
    assert out.downgraded_from == "contradicts"
    # collision path never downgrades
    out = _pair("contradicts", 0.3, {"t": 60}, {"t": 30})
    assert out.result.relation == "contradicts"
