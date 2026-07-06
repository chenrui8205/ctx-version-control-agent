"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiBase, setCfg } from "../../lib/api";
import { useT, useLocale } from "../../lib/i18n";

export default function Login() {
  const t = useT();
  const [locale, setLoc] = useLocale();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [invite, setInvite] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const body: any = { email, password };
      if (mode === "signup") {
        body.invite_code = invite;
        body.display_name = displayName;
      }
      const res = await fetch(`${apiBase()}/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
      setCfg({ url: apiBase(), repo: data.repo_id, token: data.token });
      localStorage.setItem("ctxvcs-user", JSON.stringify({
        email, display_name: data.display_name, role: data.role,
      }));
      router.push(mode === "signup" ? "/welcome" : "/wiki");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "60px auto" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>{t(mode === "login" ? "loginTitle" : "signupTitle")}</h3>
        <a style={{ cursor: "pointer" }} className="muted"
           onClick={() => setLoc(locale === "zh" ? "en" : "zh")}>
          {locale === "zh" ? "EN" : "中文"}
        </a>
      </div>
      <label>{t("email")}</label>
      <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
      <label>{t("password")}</label>
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
             onKeyDown={(e) => e.key === "Enter" && submit()} />
      {mode === "signup" && (
        <>
          <label>{t("displayName")}</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <label>{t("inviteCode")}</label>
          <input value={invite} onChange={(e) => setInvite(e.target.value)} />
        </>
      )}
      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" disabled={busy} onClick={submit}>
          {t(mode === "login" ? "login" : "signup")}
        </button>
        <a style={{ cursor: "pointer" }} className="muted"
           onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {t(mode === "login" ? "noAccount" : "haveAccount")}
        </a>
      </div>
      {err && <div className="banner-err" style={{ marginTop: 10 }}>{err}</div>}
    </div>
  );
}
