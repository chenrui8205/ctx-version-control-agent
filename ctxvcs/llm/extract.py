"""M1 server-side extraction (§8 standalone push, amended Core Decision 6).

The `ctxvcs push` path sends raw session notes; the server distills them into
candidate entries using the SAME versioned prompt as the agent skill
(`llm/prompts/extract.md`), gated by the §12.4 eval's notes fixtures (N1-N2).
"""

import json
from typing import Protocol

from ctxvcs.config import Settings, settings


class ExtractResult(dict):
    """{entries: list[dict], session_summary: str}"""


class ExtractClient(Protocol):
    def extract(
        self,
        raw_notes: str,
        subject_registry: list[str],
        entry_types: dict,
        *,
        today: str,
    ) -> ExtractResult: ...


class ClaudeExtractClient:
    def __init__(self, cfg: Settings | None = None):
        import anthropic

        from ctxvcs.llm.claude import PROMPTS

        self.cfg = cfg or settings()
        self.client = anthropic.Anthropic(max_retries=3)
        self.system = (PROMPTS / "extract.md").read_text()

    def extract(self, raw_notes, subject_registry, entry_types, *, today) -> ExtractResult:
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
            "subject_registry": subject_registry,
            "entry_types": list(entry_types),
            "raw_notes": raw_notes,
            "today": today,
        }
        msg = self.client.messages.create(
            model=self.cfg.extract_model,
            max_tokens=self.cfg.extract_max_tokens,
            system=self.system,
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit_entries"},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        return ExtractResult(entries=block.input.get("entries", []),
                             session_summary=block.input.get("session_summary", ""))
