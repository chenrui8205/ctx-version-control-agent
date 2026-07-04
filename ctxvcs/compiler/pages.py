"""Pure page renderers (§7). Pages are functions of (master tree, template version):
no LLM, no clock, no randomness — byte-stable across recompiles by construction.

Every renderer returns (content, outbound_links, input_tokens). input_tokens feed the
memoization hash; they must change iff the rendered content could change.
"""

import re

TYPE_ORDER = ["decision", "constraint", "finding", "state_change", "open_question", "next_step"]
TYPE_TITLES = {
    "decision": "Decisions",
    "constraint": "Constraints",
    "finding": "Findings",
    "state_change": "State changes",
    "open_question": "Open questions",
    "next_step": "Next steps",
}
RESERVED_SLUGS = {"index", "open-threads", "journal"}
_LINK = re.compile(r"\[\[([^\]]+)\]\]")
_SLUG_BAD = re.compile(r"[^a-z0-9-]+")


def slugify(subject_key: str) -> str:
    s = _SLUG_BAD.sub("-", subject_key.lower().replace(" ", "-")).strip("-")
    s = re.sub(r"-{2,}", "-", s) or "untitled"
    return f"s-{s}" if s in RESERVED_SLUGS else s


def _prov_line(e: dict) -> str:
    p = e.get("provenance", {})
    session = str(p.get("session_id", ""))[:8]
    return " · ".join(
        str(x) for x in [p.get("author", "?"), p.get("origin", "?"), session or "-", p.get("ts", "?")]
    )


def _scalar(v) -> bool:
    return isinstance(v, (str, int, float, bool))


def _entry_sort_key(e: dict):
    return ((e.get("provenance") or {}).get("ts") or "", str(e["entry_id"]))


def render_subject(subject_key: str, entries: list[dict], registry: set[str],
                   as_of_commit: str, histories: dict[str, list[dict]]) -> tuple[str, list[str], list[str]]:
    """entries: current master entries of this subject. histories: entry_id -> version chain."""
    entries = sorted(entries, key=_entry_sort_key, reverse=True)
    lines: list[str] = []
    section_names: list[str] = ["facts"]
    present_types = [t for t in TYPE_ORDER if any(e["type"] == t for e in entries)]
    section_names += present_types
    links: list[str] = []

    # Related: [[subject]] tokens across bodies, resolved by exact registry match (§7)
    tokens = sorted({m.group(1).strip().lower() for e in entries for m in _LINK.finditer(e["body"])})
    if tokens:
        section_names.append("related")
    multi_version = [e for e in entries if len(histories.get(str(e["entry_id"]), [])) > 1]
    if multi_version:
        section_names.append("history")

    lines += [
        "---",
        f"subject: {subject_key}",
        f"as_of_commit: {as_of_commit}",
        f"sections: [{', '.join(section_names)}]",
        "---",
        "",
        f"# {subject_key}",
        "",
        "## Facts",
        "",
    ]

    # Facts table: newest value per structured field, stable field-name ordering
    facts: dict[str, tuple[str, str]] = {}
    for e in entries:  # entries are newest-first; first writer wins per field
        for name, v in e["fields"].items():
            if name == "subject" or not _scalar(v) or name in facts:
                continue
            facts[name] = (str(v), f"{e['type']} · {_prov_line(e)}")
    if facts:
        lines += ["| Field | Value | Source |", "|---|---|---|"]
        for name in sorted(facts):
            v, src = facts[name]
            lines.append(f"| {name} | {v} | {src} |")
    else:
        lines.append("_No structured fields._")
    lines.append("")

    for t in present_types:
        lines += [f"## {TYPE_TITLES[t]}", ""]
        for e in [x for x in entries if x["type"] == t]:
            extra = {k: v for k, v in e["fields"].items() if k != "subject" and _scalar(v)}
            extras = "; ".join(f"{k}: {v}" for k, v in sorted(extra.items()))
            lines.append(f"- {e['body']}")
            if extras:
                lines.append(f"  - {extras}")
            lines.append(f"  - <sub>{_prov_line(e)}</sub>")
        lines.append("")

    if tokens:
        lines += ["## Related", ""]
        for t in tokens:
            if t in registry:
                slug = slugify(t)
                lines.append(f"- [{t}]({slug})")
                links.append(slug)
            else:
                lines.append(f"- {t}")  # unresolved: plain text in M0; redlink queue is M1
        lines.append("")

    if multi_version:
        lines += ["## History", ""]
        for e in sorted(multi_version, key=lambda x: str(x["entry_id"])):
            chain = histories[str(e["entry_id"])]
            arrow = " ← ".join(f"{v['content_hash'][:8]}" for v in chain)
            lines.append(f"- `{str(e['entry_id'])[:8]}` ({e['type']}): {arrow}")
        lines.append("")

    input_tokens = sorted(e["content_hash"] for e in entries)
    input_tokens += [f"link:{t}:{1 if t in registry else 0}" for t in tokens]
    input_tokens += [f"hist:{str(e['entry_id'])[:8]}:{len(histories.get(str(e['entry_id']), []))}"
                     for e in multi_version]
    input_tokens.append(f"as_of:{as_of_commit}")
    return "\n".join(lines).rstrip() + "\n", links, input_tokens


def render_open_threads(open_items: list[dict], head: str) -> tuple[str, list[str], list[str]]:
    """Every open open_question/next_step grouped by subject, newest first (§7).
    The landing page for picking up work."""
    by_subject: dict[str, list[dict]] = {}
    for e in open_items:
        by_subject.setdefault(e["subject_key"], []).append(e)
    groups = sorted(
        by_subject.items(),
        key=lambda kv: (max((x.get("provenance") or {}).get("ts") or "" for x in kv[1]), kv[0]),
        reverse=True,
    )
    lines = [
        "---",
        "kind: open-threads",
        f"as_of_commit: {head}",
        "---",
        "",
        "# Open threads",
        "",
    ]
    links: list[str] = []
    if not groups:
        lines.append("_Nothing open. Push a session to start a thread._")
    for subject, items in groups:
        slug = slugify(subject)
        links.append(slug)
        lines += [f"## {subject} — [page]({slug})", ""]
        for e in sorted(items, key=_entry_sort_key, reverse=True):
            f = e["fields"]
            flags = []
            if e["type"] == "open_question" and f.get("blocking"):
                flags.append("**blocking**")
            if f.get("owner"):
                flags.append(f"owner: {f['owner']}")
            suffix = (" — " + " · ".join(flags)) if flags else ""
            lines.append(f"- [ ] `{e['type']}` {e['body']}{suffix}")
            lines.append(f"  - <sub>{_prov_line(e)}</sub>")
        lines.append("")
    input_tokens = sorted(e["content_hash"] for e in open_items) + [f"as_of:{head}"]
    return "\n".join(lines).rstrip() + "\n", links, input_tokens


def render_journal(sessions: list[dict], head: str) -> tuple[str, list[str], list[str]]:
    """sessions (newest first): {commit, author, message, ts, entries_by_group, resolved}.
    The team's ledger; replaces hub/overview pages entirely (§7)."""
    lines = [
        "---",
        "kind: journal",
        f"as_of_commit: {head}",
        "---",
        "",
        "# Journal",
        "",
    ]
    links: list[str] = []
    if not sessions:
        lines.append("_No sessions yet._")
    for s in sessions:
        lines += [f"## {s['ts']} — {s['author'] or '?'} — {s['commit'][:8]}", "", s["message"].strip(), ""]
        for group, items in s["groups"]:
            if not items:
                continue
            lines.append(f"**{group}**")
            for e in items:
                slug = slugify(e["subject_key"])
                links.append(slug)
                origin = (e.get("provenance") or {}).get("origin", "?")
                lines.append(f"- [{e['subject_key']}]({slug}): {e['body']} <sub>({origin})</sub>")
            lines.append("")
        if s["resolved"]:
            lines.append("**Resolved conflicts**")
            for r in s["resolved"]:
                lines.append(f"- {r['subject_key']}: {r['decision']} <sub>(was {r['existing_hash'][:8]})</sub>")
            lines.append("")
    input_tokens = sorted(s["commit"] for s in sessions) + [f"as_of:{head}"]
    return "\n".join(lines).rstrip() + "\n", sorted(set(links)), input_tokens


def render_index(subject_stats: list[dict], n_open: int, n_sessions: int, head: str) -> tuple[str, list[str], list[str]]:
    """One line per page: slug + one-line summary + as_of_commit. The agent's routing file (§7)."""
    lines = [
        "---",
        "kind: index",
        f"as_of_commit: {head}",
        "---",
        "",
        "# Index",
        "",
        f"- [open-threads](open-threads) — {n_open} open item(s)",
        f"- [journal](journal) — {n_sessions} session(s)",
        "",
        "## Subjects",
        "",
    ]
    links = ["open-threads", "journal"]
    if not subject_stats:
        lines.append("_No subjects yet._")
    for s in sorted(subject_stats, key=lambda x: x["slug"]):
        types = ", ".join(f"{n} {t}" for t, n in sorted(s["types"].items()))
        lines.append(f"- [{s['subject_key']}]({s['slug']}) — {types} — as_of {s['as_of'][:8]}")
        links.append(s["slug"])
    input_tokens = [f"{s['slug']}:{s['as_of']}:{sum(s['types'].values())}" for s in subject_stats]
    input_tokens += [f"open:{n_open}", f"sessions:{n_sessions}", f"as_of:{head}"]
    return "\n".join(lines).rstrip() + "\n", links, sorted(input_tokens)


def parse_sections(content: str) -> list[dict]:
    """Header-anchored spans [{id, title, start, end}] over '##' headings."""
    out: list[dict] = []
    offset = 0
    for line in content.splitlines(keepends=True):
        if line.startswith("## "):
            title = line[3:].strip()
            sec_id = _SLUG_BAD.sub("-", title.lower().split(" — ")[0].split(" (")[0]).strip("-")
            if out:
                out[-1]["end"] = offset
            out.append({"id": sec_id, "title": title, "start": offset, "end": len(content)})
        offset += len(line)
    return out
