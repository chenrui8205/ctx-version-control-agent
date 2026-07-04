"""Incremental page build (§7, § Core 12): dirty-tracking by entry_id, memoization by
input_hash, bounded recompiles. Runs as a job AFTER the commit transaction. Full
rebuild is always safe — pages are a regenerable cache (§ Core 11).
"""

import hashlib
import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ctxvcs.compiler import pages as P
from ctxvcs.config import settings
from ctxvcs.dag.trees import commit_tree, diff_trees, entry_history, head_commit, walk_history
from ctxvcs.store.models import (
    CommitParent,
    Conflict,
    MergeRequest,
    PageInput,
    WikiPage,
)


def _master_entry_views(session: Session, repo_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT m.entry_id::text AS entry_id, e.content_hash, e.type, e.fields,
                   e.body, e.subject_key, e.provenance
            FROM master_entries m JOIN entries e ON e.content_hash = m.content_hash
            WHERE m.repo_id = :r
            """
        ),
        {"r": str(repo_id)},
    ).mappings()
    return [dict(r) for r in rows]


def _input_hash(tokens: list[str]) -> str:
    tv = settings().template_version
    return hashlib.sha256(("\n".join(sorted(tokens)) + "\n" + tv).encode()).hexdigest()


def _upsert_page(
    session: Session,
    repo_id: uuid.UUID,
    kind: str,
    slug: str,
    subject_key: str | None,
    source_commit: str,
    content: str,
    links: list[str],
    input_tokens: list[str],
    input_entry_ids: list[str],
) -> bool:
    """Returns True when the page was (re)written, False when memoization skipped it."""
    ih = _input_hash(input_tokens)
    existing = session.execute(
        select(WikiPage).where(WikiPage.repo_id == repo_id, WikiPage.slug == slug)
    ).scalar_one_or_none()
    if existing is not None and existing.input_hash == ih:
        return False  # unchanged input hash ⇒ zero writes (§14)
    sections = P.parse_sections(content)
    if existing is None:
        existing = WikiPage(
            page_id=uuid.uuid4(), repo_id=repo_id, kind=kind, slug=slug, subject_key=subject_key,
            source_commit=source_commit, input_hash=ih, content=content, sections=sections,
            outbound_links=links,
        )
        session.add(existing)
    else:
        existing.kind = kind
        existing.subject_key = subject_key
        existing.source_commit = source_commit
        existing.input_hash = ih
        existing.content = content
        existing.sections = sections
        existing.outbound_links = links
        session.execute(text("UPDATE wiki_pages SET compiled_at = now() WHERE page_id = :p"),
                        {"p": str(existing.page_id)})
    session.flush()
    session.execute(delete(PageInput).where(PageInput.page_id == existing.page_id))
    for eid in set(input_entry_ids):
        session.add(PageInput(page_id=existing.page_id, entry_id=uuid.UUID(eid)))
    return True


def _sessions_for_journal(session: Session, repo_id: uuid.UUID) -> list[dict]:
    commits = walk_history(session, repo_id)
    views = {v["content_hash"]: v for v in _all_entry_views(session, repo_id)}
    out = []
    for c in commits:
        parent = session.execute(
            select(CommitParent.parent_hash).where(CommitParent.commit_hash == c.hash)
        ).scalar_one_or_none()
        tree = commit_tree(session, c.hash)
        ptree = commit_tree(session, parent) if parent else {}
        d = diff_trees(ptree, tree)
        touched = [tree[eid] for eid in d["added"] + d["modified"]]
        evs = [views[ch] for ch in touched if ch in views]
        opened = [e for e in evs if e["type"] in ("open_question", "next_step")
                  and e["fields"].get("status") == "open"]
        closed = [e for e in evs if e["fields"].get("status") == "closed"]
        groups = [
            ("Decisions", [e for e in evs if e["type"] == "decision"]),
            ("Findings", [e for e in evs if e["type"] == "finding"]),
            ("State changes", [e for e in evs if e["type"] == "state_change"]),
            ("Constraints", [e for e in evs if e["type"] == "constraint"]),
            ("Opened", opened),
            ("Closed", closed),
        ]
        groups = [(g, sorted(items, key=lambda e: (e["subject_key"], e["content_hash"])))
                  for g, items in groups]
        resolved = []
        if c.session_id:
            rows = session.execute(
                select(Conflict)
                .join(MergeRequest, MergeRequest.id == Conflict.merge_request_id)
                .where(MergeRequest.staging_id == c.session_id, Conflict.status == "resolved")
            ).scalars()
            for cf in rows:
                resolved.append({
                    "subject_key": cf.subject_key,
                    "decision": (cf.proposed_resolution or {}).get("decided", "resolved"),
                    "existing_hash": cf.existing_content_hash or "",
                })
        resolved.sort(key=lambda r: r["subject_key"])
        out.append({
            "commit": c.hash,
            "author": c.author,
            "message": c.message,
            "ts": c.created_at.isoformat() if c.created_at else "",
            "groups": groups,
            "resolved": resolved,
        })
    return out


def _all_entry_views(session: Session, repo_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ce.entry_id::text AS entry_id, e.content_hash, e.type, e.fields,
                   e.body, e.subject_key, e.provenance
            FROM commit_entries ce
            JOIN commits c ON c.hash = ce.commit_hash
            JOIN entries e ON e.content_hash = ce.content_hash
            WHERE c.repo_id = :r
            """
        ),
        {"r": str(repo_id)},
    ).mappings()
    return [dict(r) for r in rows]


def compile_pages(
    session: Session,
    repo_id: uuid.UUID,
    changed_entry_ids: list[uuid.UUID] | None = None,
) -> list[str]:
    """changed_entry_ids=None ⇒ full rebuild (always safe). Returns written slugs."""
    head = head_commit(session, repo_id) or "genesis"
    views = _master_entry_views(session, repo_id)
    by_subject: dict[str, list[dict]] = {}
    for v in views:
        by_subject.setdefault(v["subject_key"], []).append(v)
    registry = set(by_subject)

    if changed_entry_ids is None:
        dirty_subjects = set(by_subject)
    else:
        changed = {str(x) for x in changed_entry_ids}
        dirty_subjects = {v["subject_key"] for v in views if v["entry_id"] in changed}
        # pages whose inputs include a changed entry (covers supersessions/closures
        # where the subject page already exists)
        rows = session.execute(
            select(WikiPage.subject_key)
            .join(PageInput, PageInput.page_id == WikiPage.page_id)
            .where(
                WikiPage.repo_id == repo_id,
                WikiPage.kind == "subject",
                PageInput.entry_id.in_([uuid.UUID(x) for x in changed]),
            )
        ).scalars()
        dirty_subjects |= {r for r in rows if r}

    written: list[str] = []

    for subject in sorted(dirty_subjects):
        entries = by_subject.get(subject, [])
        if not entries:
            continue
        histories = {e["entry_id"]: entry_history(session, repo_id, uuid.UUID(e["entry_id"]))
                     for e in entries}
        # as_of = the newest commit that introduced any current version of this subject
        # (NOT HEAD — that would break byte-stable memoization across unrelated pushes)
        intro_commits: list[tuple[str, str]] = []
        commit_order = {c.hash: i for i, c in enumerate(walk_history(session, repo_id))}
        for e in entries:
            for v in histories[e["entry_id"]]:
                if v["content_hash"] == e["content_hash"]:
                    intro_commits.append((v["commit"], v["ts"] or ""))
        as_of = min(intro_commits, key=lambda x: commit_order.get(x[0], 1 << 30))[0] if intro_commits else head
        content, links, tokens = P.render_subject(subject, entries, registry, as_of, histories)
        if _upsert_page(session, repo_id, "subject", P.slugify(subject), subject, head,
                        content, links, tokens, [e["entry_id"] for e in entries]):
            written.append(P.slugify(subject))

    open_items = [v for v in views if v["type"] in ("open_question", "next_step")
                  and v["fields"].get("status") == "open"]
    content, links, tokens = P.render_open_threads(open_items, head)
    if _upsert_page(session, repo_id, "open_threads", "open-threads", None, head, content,
                    links, tokens, [e["entry_id"] for e in open_items]):
        written.append("open-threads")

    sessions = _sessions_for_journal(session, repo_id)
    content, links, tokens = P.render_journal(sessions, head)
    if _upsert_page(session, repo_id, "journal", "journal", None, head, content, links, tokens, []):
        written.append("journal")

    subject_stats = []
    for subject, entries in by_subject.items():
        types: dict[str, int] = {}
        for e in entries:
            types[e["type"]] = types.get(e["type"], 0) + 1
        page = session.execute(
            select(WikiPage).where(WikiPage.repo_id == repo_id, WikiPage.slug == P.slugify(subject))
        ).scalar_one_or_none()
        as_of = "genesis"
        if page is not None:
            for line in page.content.splitlines():
                if line.startswith("as_of_commit: "):
                    as_of = line.split(": ", 1)[1]
                    break
        subject_stats.append({"subject_key": subject, "slug": P.slugify(subject), "types": types,
                              "as_of": as_of})
    content, links, tokens = P.render_index(subject_stats, len(open_items), len(sessions), head)
    if _upsert_page(session, repo_id, "index", "index", None, head, content, links, tokens, []):
        written.append("index")

    session.commit()
    return written


def serve_page(session: Session, repo_id: uuid.UUID, slug: str, section: str | None = None) -> dict | None:
    page = session.execute(
        select(WikiPage).where(WikiPage.repo_id == repo_id, WikiPage.slug == slug)
    ).scalar_one_or_none()
    if page is None:
        return None
    content = page.content
    # Open-conflicts overlay: joined at serve time, never compiled in (§7)
    overlay = []
    if page.kind == "subject" and page.subject_key:
        rows = session.execute(
            select(Conflict).where(
                Conflict.repo_id == repo_id,
                Conflict.subject_key == page.subject_key,
                Conflict.status == "open",
            )
        ).scalars().all()
        for cf in rows:
            overlay.append({
                "conflict_id": str(cf.id),
                "merge_request_id": str(cf.merge_request_id),
                "conflicting_fields": cf.conflicting_fields or [],
                "confidence": cf.confidence,
            })
        if rows:
            banner = ["> **⚠ Open conflicts** — this subject has contested entries awaiting review:"]
            for cf in rows:
                fields = ", ".join(cf.conflicting_fields or []) or "prose-level"
                banner.append(f"> - conflict `{str(cf.id)[:8]}` on {fields} (MR `{str(cf.merge_request_id)[:8]}`)")
            content = "\n".join(banner) + "\n\n" + content
    sections = page.sections
    if section:
        span = next((s for s in page.sections if s["id"] == section), None)
        if span is None:
            return None
        content = page.content[span["start"]:span["end"]]
        sections = [span]
    return {
        "slug": page.slug,
        "kind": page.kind,
        "subject_key": page.subject_key,
        "source_commit": page.source_commit,
        "compiled_at": page.compiled_at.isoformat() if page.compiled_at else None,
        "sections": sections,
        "open_conflicts": overlay,
        "content": content,
    }


def search_pages(session: Session, repo_id: uuid.UUID, q: str, k: int = 10) -> list[dict]:
    """Postgres FTS over compiled pages — the read-side search (§ Core 13)."""
    rows = session.execute(
        text(
            """
            SELECT slug, sections, ts_rank(fts, plainto_tsquery('english', :q)) AS rank,
                   ts_headline('english', content, plainto_tsquery('english', :q),
                               'MaxWords=25, MinWords=10') AS snippet
            FROM wiki_pages
            WHERE repo_id = :r AND fts @@ plainto_tsquery('english', :q)
            ORDER BY rank DESC LIMIT :k
            """
        ),
        {"r": str(repo_id), "q": q, "k": k},
    ).mappings()
    out = []
    for r in rows:
        out.append({"slug": r["slug"], "section_id": (r["sections"][0]["id"] if r["sections"] else None),
                    "snippet": r["snippet"], "rank": float(r["rank"])})
    return out
