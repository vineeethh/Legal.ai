"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type DocumentSummary, type KbStats, type SettingsView } from "@/lib/api";
import { DocumentsTable } from "@/components/documents-table";
import { UploadDropzone } from "@/components/upload-dropzone";
import { AnimatedNumber, Skeleton } from "@/components/ui";

const REFRESH_MS = 4000;

function LedgerRow({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-2.5 last:border-b-0">
      <div className="min-w-0">
        <div className="text-[12px] text-muted">{label}</div>
        {sub ? <div className="tnum mt-0.5 truncate text-[10.5px] text-faint">{sub}</div> : null}
      </div>
      <div className="tnum shrink-0 font-serif text-[19px] leading-none">{value}</div>
    </div>
  );
}

/** The system panel: what the pipeline knows, as a quiet ledger. */
function SystemPanel({ kb, settings }: { kb: KbStats | null; settings: SettingsView | null }) {
  return (
    <aside className="lg:sticky lg:top-[78px]">
      <div className="eyebrow">System</div>
      <div className="rule-double mt-2" />
      {kb ? (
        <div>
          <LedgerRow label="Judgments processed" value={<AnimatedNumber value={kb.total_runs} />} />
          <LedgerRow
            label="Statute sections"
            value={<AnimatedNumber value={kb.total_sections} />}
            sub="the verification source of truth"
          />
          {kb.acts.map((a) => (
            <LedgerRow key={a.act_version} label={a.act_version} value={<AnimatedNumber value={a.sections} />} />
          ))}
          <LedgerRow label="Old → new crosswalk" value={<AnimatedNumber value={kb.crosswalk_mappings} />} />
        </div>
      ) : (
        <Skeleton className="mt-3 h-40" />
      )}

      <div className="eyebrow mt-8">Decision gates</div>
      <div className="rule-double mt-2" />
      {settings ? (
        <div>
          <LedgerRow label="Auto-save at" value={`≥ ${settings.confidence_autosave_threshold.toFixed(2)}`} />
          <LedgerRow label="Review below" value={settings.confidence_review_threshold.toFixed(2)} />
          <LedgerRow label="Blind retries" value={settings.max_retries} />
        </div>
      ) : (
        <Skeleton className="mt-3 h-24" />
      )}
      {settings ? (
        <Link
          href="/settings"
          className="t-state mt-4 block truncate text-[11px] text-faint transition-colors hover:text-accent"
          title={settings.llm_model}
        >
          model · <span className="font-mono">{settings.llm_model}</span>
        </Link>
      ) : null}
    </aside>
  );
}

export default function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [kb, setKb] = useState<KbStats | null>(null);
  const [settings, setSettings] = useState<SettingsView | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const docs = await api.listDocuments();
        if (alive) setDocuments(docs);
      } catch {
        /* header health dot owns connectivity state */
      }
    }
    load();
    api.kbStats().then((s) => alive && setKb(s)).catch(() => {});
    api.getSettings().then((s) => alive && setSettings(s)).catch(() => {});
    const t = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1fr)_252px]">
      <div className="min-w-0 space-y-8">
        <div>
          <h1 className="max-w-2xl font-serif text-[34px] leading-[1.08] sm:text-[44px]">
            The record, <em className="text-accent">verifiable</em>.
          </h1>
          <div className="rule-double mt-5" />
          <p className="mt-4 max-w-xl text-[13px] leading-relaxed text-muted">
            Six isolated agents extract each judgment. A second model validates every claim against
            its verbatim span. Citations verify against the statute book in force on the decision
            date. Nothing is asserted that can&apos;t be traced.
          </p>
        </div>

        <UploadDropzone />

        {documents === null ? (
          <div className="space-y-px overflow-hidden rounded-xl border border-border">
            <Skeleton className="h-14 rounded-none" />
            <Skeleton className="h-14 rounded-none" />
            <Skeleton className="h-14 rounded-none" />
          </div>
        ) : (
          <DocumentsTable documents={documents} />
        )}
      </div>

      <SystemPanel kb={kb} settings={settings} />
    </div>
  );
}
