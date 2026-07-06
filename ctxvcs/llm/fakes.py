"""Deterministic fakes (§14). Unit tests and --mode fake evals use these; they
exercise pipeline/transaction/compiler logic independent of model quality (§12.3)."""

from ctxvcs.llm.types import ReconcileResult


class ScriptedReconcileClient:
    """Relations keyed by (incoming marker, existing marker).

    Markers come from provenance['fixture_key'] when present, else the entry body.
    Unscripted pairs return `unrelated` — scenario scripts only name the pairs
    that matter and everything else stays inert.
    """

    def __init__(self, script: dict[tuple[str, str], str] | None = None, default: str = "unrelated"):
        self.script = script or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def marker(view: dict) -> str:
        return view.get("fixture_key") or view.get("body", "")

    def classify(self, incoming, existing, *, constrained=False, conflicting_fields=()) -> ReconcileResult:
        key = (self.marker(incoming), self.marker(existing))
        self.calls.append(key)
        relation = self.script.get(key, self.default)
        return ReconcileResult(
            relation=relation,
            confidence=0.99,
            rationale=f"scripted: {key[0]!r} vs {key[1]!r}",
            conflicting_fields=list(conflicting_fields),
        )


class EchoExpectedClient:
    """Harness self-test fake for run_reconcile --mode fake: echoes the fixture's
    expected relation (first of expected_any). Validates runner plumbing, never model quality."""

    def __init__(self, expected_by_pair: dict[str, str]):
        self.expected_by_pair = expected_by_pair
        self.current_pair: str | None = None

    def classify(self, incoming, existing, *, constrained=False, conflicting_fields=()) -> ReconcileResult:
        relation = self.expected_by_pair[self.current_pair]
        return ReconcileResult(relation=relation, confidence=0.95, rationale="echo-expected fake",
                               conflicting_fields=list(conflicting_fields))


class FakeExtractClient:
    """Deterministic notes extractor: returns the JSON block embedded in the notes
    (```json {entries: [...], session_summary: "..."} ```). Tests author their notes
    with the expected extraction inline — plumbing test, never extraction quality."""

    def extract(self, raw_notes, subject_registry, entry_types, *, today):
        import json
        import re

        from ctxvcs.llm.extract import ExtractResult

        m = re.search(r"```json\s*(\{.*?\})\s*```", raw_notes, re.DOTALL)
        if not m:
            return ExtractResult(entries=[], session_summary="")
        data = json.loads(m.group(1))
        return ExtractResult(entries=data.get("entries", []),
                             session_summary=data.get("session_summary", ""))


class FakeEmbedder:
    """Deterministic sha256-seeded unit vector. Similar text does NOT embed near —
    scenario retrieval relies on subject_key equality, which is the point."""

    def __init__(self, dim: int = 1536):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import math

        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vals = [((h[i % 32] * 31 + i * 7) % 1000) / 1000.0 - 0.5 for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vals)) or 1.0
            out.append([v / norm for v in vals])
        return out
