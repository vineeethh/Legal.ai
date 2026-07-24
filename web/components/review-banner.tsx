"use client";

import { useState } from "react";
import { AlertTriangle, Bug } from "lucide-react";
import { api, type ReviewPayload } from "@/lib/api";
import { Button, Card, cn } from "@/components/ui";

// The graph's edit-resume path does a SHALLOW top-level replace — your JSON
// for e.g. "metadata" replaces that whole section, it isn't deep-merged into
// the existing fields. These are the sections it's safe to hand-edit;
// confidence/review_decision/processing are deliberately excluded (they're
// computed, not authored).
const EDITABLE_SECTIONS = ["metadata", "facts", "statutes", "petitioner", "respondent", "evidence"] as const;

/** Human-in-the-loop: the paused graph's interrupt payload, rendered for a
 *  decision. Approve keeps the record; Reject marks it human_required; Edit
 *  applies top-level JSON field overrides, re-validated before resume. */
export function ReviewBanner({
  documentId,
  payload,
  onDecided,
}: {
  documentId: string;
  payload: ReviewPayload | null;
  onDecided: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [patchText, setPatchText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  function startEditing() {
    const preview = payload?.result_preview ?? {};
    const editable: Record<string, unknown> = {};
    for (const key of EDITABLE_SECTIONS) {
      if (key in preview) editable[key] = preview[key];
    }
    setPatchText(JSON.stringify(editable, null, 2));
    setEditing(true);
  }

  async function decide(action: "approve" | "reject" | "edit") {
    setBusy(true);
    setError(null);
    try {
      let patches: Record<string, unknown> | undefined;
      if (action === "edit") {
        patches = JSON.parse(patchText);
      }
      await api.review(documentId, action, patches);
      onDecided();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit decision.");
      setBusy(false);
    }
  }

  const flagged = payload?.flagged_fields ?? [];
  const preview = (payload?.result_preview ?? {}) as Record<string, any>;
  const agentErrors: Record<string, string> = preview?.processing?.agent_errors ?? {};
  const hasAgentErrors = Object.keys(agentErrors).length > 0;

  return (
    <Card className="border-warn/40 bg-warn-soft/50 px-6 py-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-warn">
          <AlertTriangle size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-serif text-lg">Human review required</h3>
          <p className="mt-0.5 text-sm text-muted">
            Confidence {payload ? payload.confidence_score.toFixed(3) : "—"} fell below the review
            threshold. The pipeline is <strong>paused</strong> — the record will not be finalized
            until you decide.
          </p>

          {hasAgentErrors ? (
            <div className="mt-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-danger">
                <Bug size={13} />
                Extraction errors — this is likely why fields are empty
              </div>
              <p className="mb-2 text-xs text-muted">
                These agents didn&apos;t just find nothing — their calls actually failed. Fields
                are empty because the model/endpoint errored out, not because the document lacks
                that information. Fix the underlying issue (often a model or provider
                misconfiguration in Settings) and re-run.
              </p>
              {Object.entries(agentErrors).map(([agent, err]) => (
                <div key={agent} className="border-b border-danger/20 py-1.5 text-xs last:border-b-0">
                  <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px]">{agent}</span>
                  <span className="ml-2 font-mono text-[11px] text-danger">{err}</span>
                </div>
              ))}
            </div>
          ) : null}

          {flagged.length > 0 ? (
            <div className="mt-3 max-h-44 overflow-y-auto rounded-lg border border-border bg-surface px-4 py-3 text-xs pane-scroll">
              <div className="mb-1.5 font-medium uppercase tracking-wide text-faint">
                Flagged fields ({flagged.length})
              </div>
              {flagged.map((f, i) => (
                <div key={i} className="border-b border-border py-1.5 last:border-b-0">
                  <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px]">
                    {f.agent}
                  </span>
                  <span className="ml-2 font-mono text-[11px]">{f.field_path}</span>
                  {f.reason ? <div className="mt-0.5 text-muted">{f.reason}</div> : null}
                </div>
              ))}
            </div>
          ) : !hasAgentErrors ? (
            <p className="mt-2 text-xs text-muted">
              No individual fields failed validation — the score fell on aggregate signals (e.g. an
              essentially empty extraction).
            </p>
          ) : null}

          {editing ? (
            <div className="mt-3">
              <label className="text-xs font-medium text-muted">
                Editing the current record (JSON) — each top-level section (metadata, facts, ...)
                is replaced whole by what you submit here, not merged field-by-field. Re-validated
                before the record is finalized.
              </label>
              <textarea
                value={patchText}
                onChange={(e) => setPatchText(e.target.value)}
                rows={16}
                spellCheck={false}
                className={cn(
                  "mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-xs",
                  "focus:outline-2 focus:outline-accent",
                )}
              />
            </div>
          ) : null}

          {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}

          <div className="mt-4 flex flex-wrap gap-2">
            {editing ? (
              <>
                <Button disabled={busy} onClick={() => decide("edit")}>
                  Apply edits & resume
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <Button disabled={busy} onClick={() => decide("approve")}>
                  Approve & save
                </Button>
                <Button variant="secondary" disabled={busy} onClick={startEditing}>
                  Edit fields…
                </Button>
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}>
                  Reject
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
