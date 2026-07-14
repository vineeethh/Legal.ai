"use client";

import { Quote } from "lucide-react";
import type { SourceRef } from "@/lib/api";
import { Badge, Card, VerificationBadge, cn } from "@/components/ui";

/* eslint-disable @typescript-eslint/no-explicit-any */

export type OnSource = (page: number, quote: string) => void;

/** The provenance chip — the product's core interaction. Click → the exact
 *  verbatim span lights up in the source PDF. Pressed state + the viewer's
 *  one-time highlight settle communicate the causality. */
function SourceChips({ sources, onSource }: { sources?: SourceRef[]; onSource: OnSource }) {
  if (!sources?.length) return null;
  return (
    <span className="ml-2 inline-flex flex-wrap gap-1 align-baseline">
      {sources.map((s, i) => (
        <button
          key={i}
          onClick={() => onSource(s.page, s.quote)}
          title={`"${s.quote.slice(0, 140)}${s.quote.length > 140 ? "…" : ""}"`}
          className={cn(
            "t-state inline-flex items-center gap-1 rounded border border-border bg-surface px-1.5 py-px",
            "text-[10.5px] font-medium text-muted transition-[color,border-color,transform,background-color]",
            "hover:border-accent/50 hover:text-accent active:scale-95",
          )}
        >
          <Quote size={8} />
          <span className="tnum">p.{s.page}</span>
        </button>
      ))}
    </span>
  );
}

function Absent() {
  // Absence recedes; it doesn't shout. The philosophy lives in the tooltip.
  return (
    <span
      className="cursor-help text-[13px] text-faint"
      title="Not confidently found — a deliberate absence, never a guess. ('None over guessing.')"
    >
      —
    </span>
  );
}

function FieldRow({
  label,
  sourced,
  onSource,
  render,
}: {
  label: string;
  sourced: { value: any; sources?: SourceRef[] } | null | undefined;
  onSource: OnSource;
  render?: (v: any) => React.ReactNode;
}) {
  const value = sourced?.value ?? null;
  return (
    <div className="grid grid-cols-[130px_1fr] gap-4 py-2 text-[13px] leading-relaxed">
      <div className="eyebrow pt-0.5">{label}</div>
      <div className="min-w-0">
        {value === null || value === undefined || value === "" ? (
          <Absent />
        ) : (
          <>
            <span className="break-words">{render ? render(value) : String(value)}</span>
            <SourceChips sources={sourced?.sources} onSource={onSource} />
          </>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ title, hint, count }: { title: string; hint?: string; count?: number }) {
  return (
    <div className="mt-7 flex items-baseline justify-between border-b border-border-strong pb-2 first:mt-0">
      <h3 className="font-serif text-[19px] tracking-tight">
        {title}
        {typeof count === "number" ? (
          <span className="tnum ml-2 align-middle text-[11px] font-sans text-faint">{count}</span>
        ) : null}
      </h3>
      {hint ? <span className="text-[11px] text-faint">{hint}</span> : null}
    </div>
  );
}

function ItemList({
  items,
  onSource,
  render,
  emptyLabel,
}: {
  items: any[];
  onSource: OnSource;
  render: (v: any) => React.ReactNode;
  emptyLabel: string;
}) {
  if (!items?.length) return <p className="py-2.5"><Absent /></p>;
  return (
    <ul className="divide-y divide-border">
      {items.map((item, i) => (
        <li key={i} className="py-2.5 text-[13px] leading-relaxed">
          {render(item.value)}
          <SourceChips sources={item.sources} onSource={onSource} />
        </li>
      ))}
    </ul>
  );
}

export function RecordView({ result, onSource }: { result: Record<string, any>; onSource: OnSource }) {
  const meta = result.metadata ?? {};
  const facts = result.facts ?? {};
  const statutes = result.statutes?.references ?? [];
  const petitioner = result.petitioner?.arguments ?? [];
  const respondent = result.respondent?.arguments ?? [];
  const evidence = result.evidence?.items ?? [];

  return (
    <Card className="px-6 py-5">
      <SectionHeader title="Case metadata" />
      <div className="divide-y divide-border">
        <FieldRow label="Court" sourced={meta.court} onSource={onSource} />
        <FieldRow label="Bench" sourced={meta.bench} onSource={onSource} />
        <FieldRow label="Case number" sourced={meta.case_number} onSource={onSource} />
        <FieldRow label="Decision date" sourced={meta.decision_date} onSource={onSource} />
        <FieldRow label="Jurisdiction" sourced={meta.jurisdiction} onSource={onSource} />
        <div className="grid grid-cols-[130px_1fr] gap-4 py-2 text-[13px]">
          <div className="eyebrow pt-0.5">Judges</div>
          <div>
            {meta.judges?.length ? (
              meta.judges.map((j: any, i: number) => (
                <span key={i} className="mr-3">
                  {String(j.value)}
                  <SourceChips sources={j.sources} onSource={onSource} />
                </span>
              ))
            ) : (
              <Absent />
            )}
          </div>
        </div>
        {(["petitioners", "respondents"] as const).map((side) => (
          <div key={side} className="grid grid-cols-[130px_1fr] gap-4 py-2 text-[13px]">
            <div className="eyebrow pt-0.5">{side}</div>
            <div className="space-y-1">
              {meta[side]?.length ? (
                meta[side].map((p: any, i: number) => (
                  <div key={i}>
                    {p.value?.name}
                    {p.value?.role ? <span className="ml-1.5 text-[11px] text-muted">({p.value.role})</span> : null}
                    <SourceChips sources={p.sources} onSource={onSource} />
                  </div>
                ))
              ) : (
                <Absent />
              )}
            </div>
          </div>
        ))}
      </div>

      <SectionHeader title="Facts" />
      <div className="divide-y divide-border">
        <FieldRow label="Background" sourced={facts.background} onSource={onSource} />
        <FieldRow label="Incident" sourced={facts.incident_summary} onSource={onSource} />
      </div>
      <div className="eyebrow mt-4">Key facts</div>
      <ItemList
        items={facts.key_facts ?? []}
        onSource={onSource}
        render={(v) => <span>{String(v)}</span>}
        emptyLabel="No key facts extracted."
      />
      <div className="eyebrow mt-4">Timeline</div>
      <ItemList
        items={facts.timeline ?? []}
        onSource={onSource}
        render={(v) => (
          <span>
            {v.event_date ? (
              <span className="tnum mr-2.5 font-medium text-accent">{v.event_date}</span>
            ) : (
              <span className="mr-2.5 italic text-faint">undated</span>
            )}
            {v.description}
          </span>
        )}
        emptyLabel="No timeline events extracted."
      />

      <SectionHeader
        title="Statutes cited"
        count={statutes.length}
        hint="verified against the act in force on the decision date"
      />
      {statutes.length === 0 ? (
        <p className="py-2.5"><Absent /></p>
      ) : (
        <ul className="divide-y divide-border">
          {statutes.map((ref: any, i: number) => (
            <li key={i} className="py-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{ref.raw_citation}</span>
                <VerificationBadge status={ref.verification_status} />
                <SourceChips sources={ref.sources} onSource={onSource} />
              </div>
              {ref.kb_match ? (
                <div className="mt-2 border-l-2 border-border-strong pl-3 text-[12px] text-muted">
                  <span className="font-medium text-foreground">
                    {ref.kb_match.act_version} · s.{ref.kb_match.section_number}
                  </span>
                  {ref.kb_match.section_title ? ` — ${ref.kb_match.section_title}` : ""}
                  <span className="tnum ml-2 text-faint">sim {Number(ref.kb_match.similarity_score).toFixed(2)}</span>
                </div>
              ) : null}
              {ref.verification_note ? (
                <div className="mt-1.5 text-[12px] text-warn">{ref.verification_note}</div>
              ) : null}
              {ref.current_equivalent ? (
                <div className="mt-1.5 text-[12px] text-muted">
                  today:{" "}
                  <Badge tone="accent">
                    {ref.current_equivalent.act_version} s.{ref.current_equivalent.section_number}
                  </Badge>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-x-10 sm:grid-cols-2">
        {[
          { title: "Petitioner", items: petitioner },
          { title: "Respondent", items: respondent },
        ].map(({ title, items }) => (
          <div key={title}>
            <SectionHeader title={title} count={items.length} hint="isolated" />
            <ItemList
              items={items}
              onSource={onSource}
              render={(v) => (
                <span>
                  {v.summary}
                  {v.relied_on ? (
                    <span className="mt-0.5 block text-[11.5px] text-muted">relies on · {v.relied_on}</span>
                  ) : null}
                </span>
              )}
              emptyLabel="No arguments extracted."
            />
          </div>
        ))}
      </div>

      <SectionHeader title="Evidence" count={evidence.length} />
      <ItemList
        items={evidence}
        onSource={onSource}
        render={(v) => (
          <span>
            <Badge tone="neutral" className="mr-2 capitalize">{v.kind}</Badge>
            {v.label ? <span className="mr-1.5 font-medium">{v.label}</span> : null}
            {v.description}
          </span>
        )}
        emptyLabel="No evidence items extracted."
      />
    </Card>
  );
}
