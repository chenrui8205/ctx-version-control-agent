"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";

/** 溯源 (M1 §10): for each current entry on the subject — who says so, in what
 *  capacity, how it landed, and every challenge it survived. */
export default function BlamePanel({ subject, onClose }: { subject: string; onClose: () => void }) {
  const t = useT();
  const [blames, setBlames] = useState<any[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const s = await api(`/subjects/${encodeURIComponent(subject)}/entries`);
        const out = [];
        for (const e of s.entries) {
          out.push({ gist: e.gist, ...(await api(`/entries/${e.entry_id}/blame`)) });
        }
        setBlames(out);
      } catch (e: any) {
        setErr(e.message);
      }
    })();
  }, [subject]);

  return (
    <div className="card" style={{ borderLeft: "3px solid var(--accent, #7c5cff)" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{t("blameTitle")} · {subject}</h3>
        <button onClick={onClose}>{t("blameClose")}</button>
      </div>
      {err && <div className="banner-err">{err}</div>}
      {!blames && !err && <div className="muted">{t("loading")}</div>}
      {blames?.map((b, i) => (
        <div key={i} style={{ marginTop: 14 }}>
          <div><span className="tag tag-keep">{b.type}</span> <span className="muted">{b.gist}</span></div>
          {Object.entries(b.fields || {}).map(([name, f]: [string, any]) => (
            <div key={name} className="fieldrow" style={{ margin: "4px 0" }}>
              <span className="k mono">{name} = {JSON.stringify(f.value)}</span>
              <span className="muted">
                {t("blameSetBy")} {f.introduced_in.author}
                （{t(f.introduced_in.origin || "agent")}） · {f.introduced_in.commit?.slice(0, 8)}
              </span>
            </div>
          ))}
          {b.versions.map((v: any, j: number) => (
            <div key={j} style={{ marginLeft: 8, marginTop: 6 }}>
              <span className="mono muted">[{v.commit?.slice(0, 8)}]</span>{" "}
              {v.author}（{t(v.origin || "agent")}） · {t("blameVia")}{" "}
              <span className="tag tag-supersede">{v.landed?.via}</span>
              {v.landed?.via === "conflict_resolution" && (
                <span className="muted"> — {v.landed.decided} · {t("blameDecidedBy")} {v.landed.decided_by}</span>
              )}
              {v.challenges?.map((ch: any, k: number) => (
                <div key={k} className="muted" style={{ marginLeft: 16 }}>
                  ⚔ {t("blameChallenged")}: {ch.challenger}（{t(ch.challenger_origin || "agent")}）
                  {" "}{t("blameRejected")} {JSON.stringify(ch.challenged_fields)} →{" "}
                  {ch.decided} · {t("blameDecidedBy")} {ch.decided_by || "—"}
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
