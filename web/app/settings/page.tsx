"use client";

import { useEffect, useState } from "react";
import { getCfg, setCfg } from "../../lib/api";

export default function Settings() {
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
      setMsg(res.ok ? "connected ✓" : `error: ${res.status} ${await res.text()}`);
    } catch (e: any) {
      setMsg(`error: ${e.message}`);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3>Connection</h3>
      <label>API URL</label>
      <input value={url} onChange={(e) => setUrl(e.target.value)} />
      <label>Repo ID</label>
      <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="uuid from POST /repos" />
      <label>API token</label>
      <input value={token} onChange={(e) => setToken(e.target.value)} type="password" />
      <div style={{ marginTop: 14 }} className="row">
        <button className="primary" onClick={save}>Save & test</button>
        <span className={msg.startsWith("connected") ? "banner-ok" : "banner-err"}>{msg}</span>
      </div>
    </div>
  );
}
