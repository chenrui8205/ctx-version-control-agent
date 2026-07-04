import pytest

from ctxvcs.core.default_schema import DEFAULT_ENTRY_TYPES
from ctxvcs.core.entry import ValidationError, validate_entries


def _raw(**kw):
    return {"type": "finding", "subject": "s", "fields": {}, "body": "a body",
            "provenance": {"origin": "agent"}, **kw}


def test_unknown_type_rejected():
    with pytest.raises(ValidationError) as ei:
        validate_entries([_raw(type="nope")], DEFAULT_ENTRY_TYPES)
    assert "unknown entry type" in str(ei.value.violations)


def test_missing_subject_rejected():
    with pytest.raises(ValidationError):
        validate_entries([{"type": "finding", "fields": {}, "body": "b"}], DEFAULT_ENTRY_TYPES)


def test_enum_violation_rejected():
    with pytest.raises(ValidationError):
        validate_entries([_raw(fields={"confidence": "sky-high"})], DEFAULT_ENTRY_TYPES)


def test_status_default_filled_for_lifecycle_types():
    entries = validate_entries([_raw(type="next_step")], DEFAULT_ENTRY_TYPES)
    assert entries[0].fields["status"] == "open"


def test_exact_duplicates_collapse_in_batch():
    entries = validate_entries([_raw(), _raw()], DEFAULT_ENTRY_TYPES)
    assert len(entries) == 1


def test_adhoc_structured_fields_allowed():
    entries = validate_entries([_raw(fields={"consumer_timeout_seconds": 30})], DEFAULT_ENTRY_TYPES)
    assert entries[0].fields["consumer_timeout_seconds"] == 30
    assert entries[0].subject_key == "s"
