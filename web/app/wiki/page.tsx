"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import PageView from "../../components/PageView";
import { useT } from "../../lib/i18n";

const TABS = [
  { slug: "open-threads", key: "openThreads" },
  { slug: "journal", key: "journal" },
  { slug: "index", key: "index" },
];

export default function Wiki() {
  const t = useT();
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
        <input placeholder={t("searchPlaceholder")} value={q}
               onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && search()} />
        <button onClick={search}>{t("search")}</button>
      </div>
      {results && (
        <div className="card">
          <h3>{t("results")}</h3>
          {results.length === 0 && <div className="muted">{t("noMatches")}</div>}
          {results.map((r, i) => (
            <div key={i} style={{ margin: "8px 0" }}>
              <Link href={`/wiki/${r.slug}`}>{r.slug}</Link>
              <div className="muted" dangerouslySetInnerHTML={{ __html: r.snippet }} />
            </div>
          ))}
        </div>
      )}
      <div className="tabs">
        {TABS.map((tb) => (
          <a key={tb.slug} className={tab === tb.slug ? "active" : ""} onClick={() => setTab(tb.slug)}
             style={{ cursor: "pointer" }}>
            {t(tb.key)}
          </a>
        ))}
      </div>
      {err && <div className="banner-err card">{err}</div>}
      {page ? (
        <>
          <div className="muted" style={{ marginBottom: 8 }}>
            {t("asOf")} <span className="mono">{page.source_commit?.slice(0, 8)}</span> · {t("compiledAt")} {page.compiled_at?.slice(0, 19)}
          </div>
          <PageView content={page.content} />
        </>
      ) : (
        !err && <div className="muted">{t("loading")}</div>
      )}
    </div>
  );
}
