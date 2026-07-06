"use client";

import { useEffect, useState } from "react";
import { getCfg, setCfg } from "../../lib/api";
import { useT } from "../../lib/i18n";

export default function Settings() {
  const t = useT();
  const [url, setUrl] = useState("http://localhost:8000");
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const c = getCfg();
    if (c) {
      setUrl(c.url);
      setRepo(c.repo);
      setToken(c.token);
    }
  }, []);

  async function save() {
    setCfg({ url, repo, token });
    try {
      const res = await fetch(`${url}/repos/${repo}/wiki/index`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setMsg(res.ok ? t("connected") : `error: ${res.status} ${await res.text()}`);
    } catch (e: any) {
      setMsg(`error: ${e.message}`);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3>{t("connection")}</h3>
      <label>{t("apiUrl")}</label>
      <input value={url} onChange={(e) => setUrl(e.target.value)} />
      <label>{t("repoId")}</label>
      <input value={repo} onChange={(e) => setRepo(e.target.value)} />
      <label>{t("apiToken")}</label>
      <input value={token} onChange={(e) => setToken(e.target.value)} type="password" />
      <div style={{ marginTop: 14 }} className="row">
        <button className="primary" onClick={save}>{t("saveTest")}</button>
        <span className={msg === t("connected") ? "banner-ok" : "banner-err"}>{msg}</span>
      </div>
    </div>
  );
}
