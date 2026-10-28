import { useState } from "react";

import { getApiKey, setApiKey } from "../api";
import type { Health } from "../types";

export function SettingsPage({ health }: { health: Health | null }) {
  const [key, setKey] = useState(getApiKey);
  const [saved, setSaved] = useState(false);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p className="muted">Connection to the Legal.ai API.</p>
        </div>
      </div>
      <div className="stack" style={{ maxWidth: 640 }}>
        <div className="card">
          <h2>API</h2>
          <dl className="fields">
            <dt>Status</dt>
            <dd>{health ? <span className="badge ok">Connected</span> : <span className="badge bad">Not reachable</span>}</dd>
            <dt>Mode</dt>
            <dd>{health ? (health.mode === "demo" ? "Demo (synthetic results)" : "Live pipeline") : "—"}</dd>
            <dt>Version</dt>
            <dd>{health?.version ?? "—"}</dd>
            <dt>Auth</dt>
            <dd>{health ? (health.auth_required ? "API key required" : "Open (no API key set on the server)") : "—"}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>API key</h2>
          <p className="muted small" style={{ marginTop: 0 }}>
            Sent as the <code>X-API-Key</code> header. Stored only in this browser.
          </p>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              setApiKey(key.trim());
              setSaved(true);
            }}
          >
            <input
              type="password"
              value={key}
              placeholder="Paste the server's API_KEY"
              onChange={(e) => {
                setKey(e.target.value);
                setSaved(false);
              }}
              style={{ flex: 1, minWidth: 200 }}
              autoComplete="off"
            />
            <button className="btn primary" type="submit">
              Save
            </button>
          </form>
          {saved && <p className="small" style={{ color: "var(--ok)", marginBottom: 0 }}>Saved.</p>}
        </div>
      </div>
    </>
  );
}
