"use client";

import { useState } from "react";
import Link from "next/link";
import { useT } from "../../lib/i18n";
import { apiBase } from "../../lib/api";

function Cmd({ text }: { text: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div className="row" style={{ margin: "6px 0" }}>
      <code className="mono" style={{ background: "var(--bg2, #f4f4f4)", padding: "6px 10px",
                                      borderRadius: 6, flex: 1, overflowX: "auto" }}>{text}</code>
      <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); }}>
        {copied ? t("copied") : t("copy")}
      </button>
    </div>
  );
}

export default function Welcome() {
  const t = useT();
  const api = apiBase();
  const web = typeof window === "undefined" ? "" : window.location.origin;
  const local = api.startsWith("http://localhost");
  const install = "pipx install \"git+https://github.com/YOUR_ORG/ctx-version-control-agent#subdirectory=cli\"";
  const login = local ? "ctxvcs login --api http://localhost:8000 --web http://localhost:3000"
                      : `ctxvcs login --api ${api} --web ${web}`;
  return (
    <div className="card" style={{ maxWidth: 640, margin: "40px auto" }}>
      <h3>{t("welcomeTitle")}</h3>
      <p><strong>{t("welcomeStep1")}</strong></p>
      <Cmd text={install} />
      <p><strong>{t("welcomeStep2")}</strong></p>
      <Cmd text={login} />
      <p><strong>ctxvcs push</strong></p>
      <p className="muted">{t("welcomeStep3")}</p>
      <p className="muted">{t("welcomeRead")}</p>
      <Link href="/wiki"><button className="primary">{t("welcomeGo")}</button></Link>
    </div>
  );
}
