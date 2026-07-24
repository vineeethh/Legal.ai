"use client";

import { useEffect, useState } from "react";
import { Bug } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, Skeleton } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */

type LogRow = {
  agent: string;
  attempt: number;
  field_path: string;
  status: string;
  reason: string | null;
};

/** "Trust or knowingly distrust" made tangible: the exact model, the prompt
 *  hashes the record was produced with, every retry, and every field-level
 *  validation verdict — straight from the persisted run. */
export function AuditTrail({
  documentId,
  processing,
  langfuseSessionId,
}: {
  documentId: string;
  processing: Record<string, any> | null;
  langfuseSessionId?: string | null;
}) {
  const [logs, setLogs] = useState<LogRow[] | null>(null);

  useEffect(() => {
    api.getValidation(documentId).then(setLogs).catch(() => setLogs([]));
  }, [documentId]);

  const promptVersions: Record<string, string> = processing?.prompt_versions ?? {};
  const retryCounts: Record<string, number> = processing?.retry_counts ?? {};
  const agentErrors: Record<string, string> = processing?.agent_errors ?? {};

  return (
    <div className="space-y-5">
      {Object.keys(agentErrors).length > 0 ? (
        <Card className="overflow-hidden border-danger/30">
          <div className="eyebrow flex items-center gap-1.5 border-b border-danger/20 bg-danger-soft px-5 py-2.5 text-danger">
            <Bug size={13} />
            Extraction errors
          </div>
          <div className="px-5 py-4 text-[12.5px]">
            <p className="mb-2 text-muted">
              These agents failed outright (not &quot;found nothing&quot; — an actual error) and
              degraded to an empty output. This is almost always a model/provider misconfiguration
              — check Settings.
            </p>
            {Object.entries(agentErrors).map(([agent, err]) => (
              <div key={agent} className="border-b border-border py-1.5 last:border-b-0">
                <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px]">{agent}</span>
                <span className="ml-2 font-mono text-[11px] text-danger">{err}</span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card className="overflow-hidden">
        <div className="eyebrow border-b border-border px-5 py-2.5">Provenance of this record</div>
        <div className="grid gap-x-8 gap-y-3 px-5 py-4 text-[12.5px] sm:grid-cols-2">
          <div>
            <div className="eyebrow">Model</div>
            <div className="mt-1 font-mono text-[12px]">{processing?.llm_model ?? "—"}</div>
          </div>
          <div>
            <div className="eyebrow">Schema · processed</div>
            <div className="tnum mt-1">
              v{processing?.schema_version ?? "?"} ·{" "}
              {processing?.processed_at ? new Date(processing.processed_at).toLocaleString() : "—"}
            </div>
          </div>
          <div>
            <div className="eyebrow">Document / trace id</div>
            <div className="mt-1 font-mono text-[11px] text-muted">
              {processing?.document_id ?? documentId}
              {langfuseSessionId ? " · langfuse session = same id" : ""}
            </div>
          </div>
          <div>
            <div className="eyebrow">Retries used</div>
            <div className="tnum mt-1 text-muted">
              {Object.entries(retryCounts)
                .filter(([, n]) => Number(n) > 0)
                .map(([agent, n]) => `${agent} ×${n}`)
                .join("  ·  ") || "none"}
            </div>
          </div>
        </div>
        <div className="border-t border-border px-5 py-4">
          <div className="eyebrow">Prompt hashes (a prompt edit changes the hash — runs are comparable only when these match)</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.keys(promptVersions).length ? (
              Object.entries(promptVersions).map(([agent, hash]) => (
                <span
                  key={agent}
                  className="rounded border border-border bg-surface-2 px-2 py-1 font-mono text-[10.5px] text-muted"
                >
                  {agent} <span className="text-faint">{hash}</span>
                </span>
              ))
            ) : (
              <span className="text-[12px] text-faint">—</span>
            )}
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="eyebrow flex items-center justify-between border-b border-border px-5 py-2.5">
          <span>Validation log</span>
          {logs ? (
            <span className="tnum normal-case tracking-normal">{logs.length} verdicts</span>
          ) : null}
        </div>
        {logs === null ? (
          <div className="space-y-px p-4">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : logs.length === 0 ? (
          <p className="px-5 py-6 text-[13px] text-faint">
            No field-level verdicts — nothing was extracted with sources to validate (empty fields
            are deliberate absences, not failures).
          </p>
        ) : (
          <ul className="max-h-[420px] overflow-y-auto pane-scroll">
            {logs.map((log, i) => (
              <li
                key={i}
                className="grid grid-cols-[90px_44px_1fr_60px] items-baseline gap-3 border-b border-border px-5 py-2 text-[12px] last:border-b-0"
              >
                <span className="font-mono text-[11px] text-muted">{log.agent}</span>
                <span className="tnum text-faint">try {log.attempt + 1}</span>
                <span className="min-w-0">
                  <span className="break-all font-mono text-[11px]">{log.field_path}</span>
                  {log.reason ? <span className="mt-0.5 block text-muted">{log.reason}</span> : null}
                </span>
                <Badge tone={log.status === "pass" ? "success" : log.status === "fail" ? "danger" : "neutral"}>
                  {log.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
