"use client";

import { useState } from "react";

function Fields({ fields, hot }: { fields: Record<string, any>; hot: string[] }) {
  return (
    <div>
      {Object.entries(fields || {})
        .filter(([k]) => k !== "subject")
        .map(([k, v]) => (
          <div key={k} className={`fieldrow ${hot.includes(k) ? "hot" : ""}`}>
            <span className="k">{k}</span>
            <span className="v">{JSON.stringify(v)}</span>
          </div>
        ))}
    </div>
  );
}

function Side({ title, entry, cls, commit, hot }: any) {
  const prov = entry?.provenance || {};
  return (
    <div className={`pane ${cls}`}>
      <h4>{title}</h4>
      <div className="row" style={{ marginBottom: 6 }}>
        <span className={`tag tag-origin-${prov.origin || "agent"}`}>{prov.origin || "?"}</span>
        <span className="muted">{prov.author || "?"} · {prov.ts || "?"}</span>
        {prov.session_id && <span className="muted mono">session {String(prov.session_id).slice(0, 8)}</span>}
        {commit && <span className="muted mono">commit {commit.slice(0, 8)}</span>}
      </div>
      <div style={{ margin: "8px 0" }}>{entry?.body}</div>
      <Fields fields={entry?.fields} hot={hot} />
    </div>
  );
}

export default function ConflictCard({ conflict, onResolve, busy }: {
  conflict: any;
  onResolve: (decision: any) => void;
  busy: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const hot = conflict.conflicting_fields || [];
  const decided = conflict.proposed_resolution?.decision?.action || conflict.proposed_resolution?.decided;

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="tag tag-conflict">contradicts</span>
        <strong>{conflict.subject_key}</strong>
        {hot.length > 0 && <span className="muted">fields: {hot.join(", ")}</span>}
        <span className="muted">confidence {(conflict.confidence ?? 0).toFixed(2)}</span>
        {(conflict.status !== "open" || decided) && <span className="tag tag-keep">{decided || conflict.status}</span>}
      </div>
      <div className="muted" style={{ marginBottom: 10 }}>
        {conflict.proposed_resolution?.rationale}
      </div>
      <div className="sidebyside">
        <Side title="Current on master" entry={conflict.existing} cls="existing"
              commit={conflict.existing_commit} hot={hot} />
        <Side title="Incoming" entry={conflict.incoming} cls="incoming" hot={hot} />
      </div>
      {conflict.status === "open" && !decided && (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" disabled={busy}
                  onClick={() => onResolve({ action: "keep_incoming" })}>
            Accept incoming
          </button>
          <button disabled={busy} onClick={() => onResolve({ action: "keep_existing" })}>
            Keep existing
          </button>
          <button disabled={busy} onClick={() => {
            setDraft(JSON.stringify({ fields: conflict.incoming?.fields, body: conflict.incoming?.body }, null, 2));
            setEditing(!editing);
          }}>
            Edit…
          </button>
        </div>
      )}
      {editing && (
        <div style={{ marginTop: 10 }}>
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" disabled={busy} onClick={() => {
              try {
                onResolve({ action: "edit", edited: JSON.parse(draft) });
                setEditing(false);
              } catch { alert("invalid JSON"); }
            }}>
              Resolve with edit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
