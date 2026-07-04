"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import PageView from "../../components/PageView";

const TABS = [
  { slug: "open-threads", label: "Open threads" },
  { slug: "journal", label: "Journal" },
  { slug: "index", label: "Index" },
];

export default function Wiki() {
  const [tab, setTab] = useState("open-threads"); // the landing tab (§10)
  const [page, setPage] = useState<any>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[] | null>(null);

  useEffect(() => {
    setPage(null);
    api(`/wiki/page/${tab}`).then(setPage).catch((e) => setErr(e.message));
  }, [tab]);

  async function search() {
    if (!q.trim()) { setResults(null); return; }
    const d = await api(`/wiki/search?q=${encodeURIComponent(q)}&k=10`);
    setResults(d.results);
  }

  return (
    <div>
      <div className="searchbox">
        <input placeholder="Search the working context…" value={q}
               onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && search()} />
        <button onClick={search}>Search</button>
      </div>
      {results && (
        <div className="card">
          <h3>Results</h3>
          {results.length === 0 && <div className="muted">no matches</div>}
          {results.map((r, i) => (
            <div key={i} style={{ margin: "8px 0" }}>
              <Link href={`/wiki/${r.slug}`}>{r.slug}</Link>
              <div className="muted" dangerouslySetInnerHTML={{ __html: r.snippet }} />
            </div>
          ))}
        </div>
      )}
      <div className="tabs">
        {TABS.map((t) => (
          <a key={t.slug} className={tab === t.slug ? "active" : ""} onClick={() => setTab(t.slug)}
             style={{ cursor: "pointer" }}>
            {t.label}
          </a>
        ))}
      </div>
      {err && <div className="banner-err card">{err}</div>}
      {page ? (
        <>
          <div className="muted" style={{ marginBottom: 8 }}>
            as of <span className="mono">{page.source_commit?.slice(0, 8)}</span> · compiled {page.compiled_at?.slice(0, 19)}
          </div>
          <PageView content={page.content} />
        </>
      ) : (
        !err && <div className="muted">loading…</div>
      )}
    </div>
  );
}
