#!/usr/bin/env python
"""Skill extraction eval (§12.4): T1–T3 transcripts → entries, scored with hard gates.

Gates:
  schema-validity 100% (deterministic)          — every extracted entry passes JSON Schema
  subject reuse >= 4/5 reusable slots on T3     — the anti-sprawl gate
  expected-item recall >= 80% across T1–T3      — judged (pinned judge, evals/judge/)
  hallucinated decisions == 0                   — judged: every decision grounded in transcript

Modes:
  fake — scripted extractor echoes expected items; recall/grounding become deterministic.
         Validates runner plumbing in CI.
  live — real extraction (llm/prompts/extract.md) + pinned judge. EVAL_LIVE=1 required.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxvcs.config import settings  # noqa: E402
from ctxvcs.core.default_schema import DEFAULT_ENTRY_TYPES  # noqa: E402
from ctxvcs.core.entry import ValidationError, validate_entries  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures" / "skill"
REPORTS = ROOT / "reports"
JUDGE = ROOT / "judge"

RECALL_GATE = 0.8
T3_REUSE_GATE = 4  # of 5 reusable slots


def load() -> tuple[dict, dict, dict]:
    expected = json.loads((FIX / "expected_items.json").read_text())
    registry = json.loads((FIX / "t3_registry.json").read_text())
    transcripts = {t: (FIX / f"{t}_transcript.md").read_text() for t in ("t1", "t2", "t3")}
    return expected, registry, transcripts


# ---------------- extractors ----------------

def fake_extract(tid: str, transcript: str, registry: list[str], expected: dict) -> list[dict]:
    """Echo expected items as entries — plumbing self-test only."""
    out = []
    for it in expected[tid]:
        subject = it.get("subject") or f"{tid}-subject-{it['type']}"
        fields: dict = {}
        if it["type"] in ("open_question", "next_step"):
            fields["status"] = "closed" if "closed" in it["gist"] else "open"
        if it["type"] == "constraint":
            fields.update({"kind": "legal", "hard": True})
        if it["type"] == "decision":
            fields["chosen"] = it["gist"][:60]
        out.append({"type": it["type"], "subject": subject, "fields": fields, "body": it["gist"],
                    "provenance": {"origin": it["origin"], "ts": "2026-07-04"}})
    return out


def live_extract(tid: str, transcript: str, registry: list[str]) -> list[dict]:
    import anthropic

    from ctxvcs.llm.claude import PROMPTS

    cfg = settings()
    client = anthropic.Anthropic(max_retries=3)
    tool = {
        "name": "submit_entries",
        "description": "Submit the distilled session entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entries": {"type": "array", "items": {"type": "object"}},
                "session_summary": {"type": "string"},
            },
            "required": ["entries", "session_summary"],
        },
    }
    payload = {
        "subject_registry": registry,
        "entry_types": list(DEFAULT_ENTRY_TYPES),
        "transcript": transcript,
        "today": "2026-07-04",
    }
    msg = client.messages.create(
        model=cfg.reconcile_model,
        max_tokens=4096,
        system=(PROMPTS / "extract.md").read_text(),
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_entries"},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    return block.input.get("entries", [])


# ---------------- judge ----------------

class Judge:
    def __init__(self, mode: str):
        self.mode = mode
        self.cfg = json.loads((JUDGE / "judge_config.json").read_text())
        self.rubric = (JUDGE / self.cfg["rubric"]).read_text()
        self.verdicts: list[dict] = []
        if mode == "live":
            import anthropic

            self.client = anthropic.Anthropic(max_retries=3)

    def _ask(self, task: str, payload: dict, schema: dict) -> dict:
        msg = self.client.messages.create(
            model=self.cfg["model"],
            max_tokens=512,
            system=self.rubric,
            tools=[{"name": "verdict", "description": f"Answer Task {task}.",
                    "input_schema": schema}],
            tool_choice={"type": "tool", "name": "verdict"},
            messages=[{"role": "user", "content": f"Task {task}.\n" + json.dumps(payload, ensure_ascii=False)}],
        )
        out = next(b for b in msg.content if b.type == "tool_use").input
        self.verdicts.append({"task": task, "payload_gist": payload.get("expected", payload.get("decision")),
                              "verdict": out})
        return out

    def covered(self, expected_item: dict, entries: list[dict], transcript: str) -> bool:
        if self.mode == "fake":
            return any(e["body"] == expected_item["gist"] for e in entries)
        out = self._ask("A", {"expected": expected_item,
                              "entries": [{"i": i, **{k: e.get(k) for k in ("type", "subject", "fields", "body")}}
                                          for i, e in enumerate(entries)]},
                        {"type": "object",
                         "properties": {"covered": {"type": "boolean"}, "by_index": {"type": "integer"}},
                         "required": ["covered"]})
        return bool(out.get("covered"))

    def grounded(self, decision: dict, transcript: str) -> bool:
        if self.mode == "fake":
            return True
        out = self._ask("B", {"decision": {k: decision.get(k) for k in ("subject", "fields", "body")},
                              "transcript": transcript},
                        {"type": "object",
                         "properties": {"grounded": {"type": "boolean"}, "quote": {"type": "string"}},
                         "required": ["grounded"]})
        return bool(out.get("grounded"))


# ---------------- scoring ----------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fake", "live"], default="fake")
    args = ap.parse_args()
    if args.mode == "live" and os.environ.get("EVAL_LIVE") != "1":
        print("live run refused: set EVAL_LIVE=1 (§12.1)", file=sys.stderr)
        return 2
    if args.mode == "live":
        cfg = settings()
        # 3 extractions + one Task-A judge call per expected item (12) + Task-B per decision (~3)
        print(f"live eval: ~18 calls to {cfg.reconcile_model} (3 extractions + judge passes)")

    expected, registry, transcripts = load()
    reg_subjects = [s["subject_key"] for s in registry["subjects"]]

    per_t: dict[str, dict] = {}
    schema_valid = True
    violations: list = []
    judge = Judge(args.mode)
    all_expected = 0
    all_covered = 0
    hallucinated: list[dict] = []
    t3_reused = 0
    t3_total_entries = 0

    for tid in ("t1", "t2", "t3"):
        if args.mode == "fake":
            entries = fake_extract(tid, transcripts[tid], reg_subjects, expected)
        else:
            entries = live_extract(tid, transcripts[tid], reg_subjects)
        try:
            validate_entries(entries, DEFAULT_ENTRY_TYPES)
        except ValidationError as ve:
            schema_valid = False
            violations.append({tid: ve.violations})
        cov = []
        for it in expected[tid]:
            ok = judge.covered(it, entries, transcripts[tid])
            cov.append((it["id"], ok))
            all_expected += 1
            all_covered += int(ok)
        for e in entries:
            if e.get("type") == "decision" and not judge.grounded(e, transcripts[tid]):
                hallucinated.append({tid: e.get("body")})
        if tid == "t3":
            t3_total_entries = len(entries)
            t3_reused = sum(1 for e in entries
                            if (e.get("subject") or e.get("fields", {}).get("subject", "")).lower().strip()
                            in reg_subjects)
        per_t[tid] = {"n_entries": len(entries), "coverage": cov,
                      "entries": [{k: e.get(k) for k in ("type", "subject", "fields", "body")}
                                  for e in entries]}

    recall = all_covered / all_expected if all_expected else 0.0
    gates = {
        "schema validity == 100%": schema_valid,
        f"T3 subject reuse >= {T3_REUSE_GATE}/{expected['t3_reusable_slots']}": t3_reused >= T3_REUSE_GATE,
        f"expected-item recall >= {RECALL_GATE:.0%}": recall >= RECALL_GATE,
        "hallucinated decisions == 0": len(hallucinated) == 0,
    }
    passed = all(gates.values())

    ts = datetime.now(UTC)
    lines = [f"# Skill extraction eval — {args.mode} — {ts.strftime('%Y-%m-%d %H:%M:%SZ')}", "",
             f"**RESULT: {'PASS' if passed else 'FAIL'}** — recall {all_covered}/{all_expected} "
             f"({recall:.0%}), T3 reuse {t3_reused}/{t3_total_entries} entries on registry subjects", "",
             "| gate | status |", "|---|---|"]
    for g, ok in gates.items():
        lines.append(f"| {g} | {'✅ pass' if ok else '❌ FAIL'} |")
    for tid, d in per_t.items():
        lines += ["", f"## {tid} — {d['n_entries']} entries extracted", ""]
        for eid, ok in d["coverage"]:
            lines.append(f"- {'✅' if ok else '❌'} {eid}")
        lines += ["", "```json", json.dumps(d["entries"], indent=2, ensure_ascii=False), "```"]
    if violations:
        lines += ["", "## Schema violations", "```json", json.dumps(violations, indent=2), "```"]
    if hallucinated:
        lines += ["", "## Hallucinated decisions", "```json", json.dumps(hallucinated, indent=2), "```"]
    if judge.verdicts and args.mode == "live":
        lines += ["", f"## Judge verdicts ({len(judge.verdicts)}) — spot-check the first 20 (§12.4)",
                  "```json", json.dumps(judge.verdicts[:20], indent=2, ensure_ascii=False), "```"]
    report = "\n".join(lines) + "\n"
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{ts.strftime('%Y%m%d-%H%M%S')}-skill-{args.mode}.md"
    out.write_text(report)
    print(report)
    print(f"report written: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
