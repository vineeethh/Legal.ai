import { useState } from "react";

import { api } from "../api";
import { AGENT_LABEL } from "../format";
import type { ReviewAction, ReviewPayload } from "../types";

/** Shown while the graph is paused at human_review (confidence < 0.80). */
export function ReviewPanel({ documentId, payload, onDone }: { documentId: string; payload: ReviewPayload; onDone: () => void }) {
  const [mode, setMode] = useState<"choose" | "edit">("choose");
  const [patchText, setPatchText] = useState(() =>
    JSON.stringify({ metadata: payload.result_preview.metadata }, null, 2),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: ReviewAction) {
    setBusy(true);
    setError(null);
    try {
      await api.submitReview(documentId, decision);
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  function submitEdit() {
    let patches: Record<string, unknown>;
    try {
      patches = JSON.parse(patchText);
    } catch {
      setError("That isn't valid JSON.");
      return;
    }
    if (typeof patches !== "object" || patches === null || Array.isArray(patches)) {
      setError("Patches must be a JSON object of top-level fields, e.g. {\"metadata\": {...}}.");
      return;
    }
    submit({ action: "edit", patches });
  }

  return (
    <div className="card" style={{ borderColor: "var(--warn)" }}>
      <div className="row" style={{ marginBottom: 8 }}>
        <h2>Your review is needed</h2>
        <span className="spacer" />
        <span className="badge bad">confidence {payload.confidence_score.toFixed(3)}</span>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        The score fell below 0.80, so the pipeline paused before saving. Check the flagged fields against their sources
        below, then decide. The run continues from exactly where it stopped.
      </p>

      {payload.flagged_fields.length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Field</th>
                <th>Why it was flagged</th>
              </tr>
            </thead>
            <tbody>
              {payload.flagged_fields.map((f, i) => (
                <tr key={i}>
                  <td>{AGENT_LABEL[f.agent] ?? f.agent}</td>
                  <td className="mono">{f.field_path}</td>
                  <td className="small">{f.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mode === "edit" && (
        <div className="stack" style={{ gap: 8, marginBottom: 12 }}>
          <label className="small muted" htmlFor="patches">
            Replace top-level fields (metadata, facts, statutes, petitioner, respondent, evidence). Every value must keep
            at least one source. The API validates the result before the run resumes.
          </label>
          <textarea id="patches" value={patchText} onChange={(e) => setPatchText(e.target.value)} spellCheck={false} />
        </div>
      )}

      {error && (
        <div className="callout bad small" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      <div className="row">
        {mode === "choose" ? (
          <>
            <button className="btn ok" disabled={busy} onClick={() => submit({ action: "approve" })}>
              Approve and save
            </button>
            <button className="btn" disabled={busy} onClick={() => setMode("edit")}>
              Edit first…
            </button>
            <button className="btn danger" disabled={busy} onClick={() => submit({ action: "reject" })}>
              Reject
            </button>
          </>
        ) : (
          <>
            <button className="btn primary" disabled={busy} onClick={submitEdit}>
              Save edits and continue
            </button>
            <button className="btn" disabled={busy} onClick={() => setMode("choose")}>
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
