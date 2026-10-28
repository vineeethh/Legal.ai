import { useState, type ReactNode } from "react";

import { ACT_LABEL, formatDate } from "../format";
import type { ArgumentsOutput, EvidenceKind, SourceRef, Sourced, StructuredJudgment } from "../types";
import { VerificationBadge } from "./Badges";
import { SourceChips } from "./Source";

type Tab = "overview" | "facts" | "statutes" | "arguments" | "evidence";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Case details" },
  { id: "facts", label: "Facts" },
  { id: "statutes", label: "Statutes" },
  { id: "arguments", label: "Arguments" },
  { id: "evidence", label: "Evidence" },
];

function Absent() {
  return (
    <span className="absent" title="Not confidently found — the pipeline returns nothing rather than guessing.">
      Not found
    </span>
  );
}

function Value({ label, text, sources }: { label: string; text: ReactNode; sources: SourceRef[] }) {
  return (
    <span className="value-line">
      <span>{text}</span>
      <SourceChips sources={sources} label={label} value={typeof text === "string" ? text : label} />
    </span>
  );
}

function ScalarRow({ label, field, format }: { label: string; field: Sourced<string>; format?: (v: string) => string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {field.value === null ? (
          <Absent />
        ) : (
          <Value label={label} text={format ? format(field.value) : field.value} sources={field.sources} />
        )}
      </dd>
    </>
  );
}

function Overview({ r }: { r: StructuredJudgment }) {
  const md = r.metadata;
  return (
    <dl className="fields">
      <ScalarRow label="Court" field={md.court} />
      <ScalarRow label="Case number" field={md.case_number} />
      <ScalarRow label="Decision date" field={md.decision_date} format={formatDate} />
      <ScalarRow label="Bench" field={md.bench} />
      <dt>Judges</dt>
      <dd>
        {md.judges.length ? (
          <div className="stack" style={{ gap: 4 }}>
            {md.judges.map((j, i) => (
              <Value key={i} label="Judge" text={j.value} sources={j.sources} />
            ))}
          </div>
        ) : (
          <Absent />
        )}
      </dd>
      <dt>Petitioners</dt>
      <dd>
        {md.petitioners.length ? (
          md.petitioners.map((p, i) => (
            <Value key={i} label="Petitioner" text={`${p.value.name}${p.value.role ? ` (${p.value.role})` : ""}`} sources={p.sources} />
          ))
        ) : (
          <Absent />
        )}
      </dd>
      <dt>Respondents</dt>
      <dd>
        {md.respondents.length ? (
          md.respondents.map((p, i) => (
            <Value key={i} label="Respondent" text={`${p.value.name}${p.value.role ? ` (${p.value.role})` : ""}`} sources={p.sources} />
          ))
        ) : (
          <Absent />
        )}
      </dd>
      <ScalarRow label="Jurisdiction" field={md.jurisdiction} />
    </dl>
  );
}

function Facts({ r }: { r: StructuredJudgment }) {
  const f = r.facts;
  return (
    <div className="stack" style={{ gap: 24 }}>
      <dl className="fields">
        <ScalarRow label="Background" field={f.background} />
        <ScalarRow label="Incident" field={f.incident_summary} />
      </dl>
      <div>
        <h3 style={{ marginBottom: 10 }}>Key facts</h3>
        {f.key_facts.length ? (
          <ul className="items">
            {f.key_facts.map((k, i) => (
              <li key={i}>
                <Value label="Key fact" text={k.value} sources={k.sources} />
              </li>
            ))}
          </ul>
        ) : (
          <Absent />
        )}
      </div>
      <div>
        <h3 style={{ marginBottom: 10 }}>Timeline</h3>
        {f.timeline.length ? (
          <ol className="timeline">
            {f.timeline.map((t, i) => (
              <li key={i}>
                <div className="muted small">{t.value.event_date ? formatDate(t.value.event_date) : "Undated"}</div>
                <Value label="Timeline event" text={t.value.description} sources={t.sources} />
              </li>
            ))}
          </ol>
        ) : (
          <Absent />
        )}
      </div>
    </div>
  );
}

function Statutes({ r }: { r: StructuredJudgment }) {
  const [open, setOpen] = useState<number | null>(null);
  const refs = r.statutes.references;
  if (!refs.length) return <Absent />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Citation</th>
            <th>Act · section</th>
            <th>Check</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {refs.map((s, i) => (
            <tr key={i}>
              <td>
                <Value label="Citation" text={s.raw_citation} sources={s.sources} />
              </td>
              <td>
                {ACT_LABEL[s.parsed_act] ?? s.parsed_act}
                {s.parsed_section ? ` · s.${s.parsed_section}` : ""}
                {s.current_equivalent && (
                  <div className="muted small">
                    Now: {ACT_LABEL[s.current_equivalent.act] ?? s.current_equivalent.act} s.
                    {s.current_equivalent.section_number}
                  </div>
                )}
              </td>
              <td>
                <VerificationBadge status={s.verification_status} />
              </td>
              <td className="small">
                {s.verification_note && <div className="muted">{s.verification_note}</div>}
                {s.kb_match && (
                  <>
                    <button className="btn small" style={{ marginTop: 4 }} onClick={() => setOpen(open === i ? null : i)}>
                      {open === i ? "Hide" : "Show"} official text
                    </button>
                    {open === i && (
                      <div className="official">
                        {s.kb_match.official_text}
                        <div className="muted small" style={{ marginTop: 6 }}>
                          {s.kb_match.act_version} · similarity {s.kb_match.similarity_score.toFixed(2)}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Side({ title, side }: { title: string; side: ArgumentsOutput }) {
  return (
    <div>
      <h3 style={{ marginBottom: 10 }}>{title}</h3>
      {side.arguments.length ? (
        <ul className="items">
          {side.arguments.map((a, i) => (
            <li key={i}>
              <Value label={`${title} argument`} text={a.value.summary} sources={a.sources} />
              {a.value.relied_on && <div className="muted small">Relies on: {a.value.relied_on}</div>}
            </li>
          ))}
        </ul>
      ) : (
        <Absent />
      )}
    </div>
  );
}

function Arguments({ r }: { r: StructuredJudgment }) {
  return (
    <div className="grid-2">
      <Side title="Petitioner" side={r.petitioner} />
      <Side title="Respondent" side={r.respondent} />
    </div>
  );
}

const KINDS: { kind: EvidenceKind; label: string }[] = [
  { kind: "witness", label: "Witnesses" },
  { kind: "document", label: "Documents" },
  { kind: "physical", label: "Physical" },
  { kind: "digital", label: "Digital" },
];

function Evidence({ r }: { r: StructuredJudgment }) {
  const items = r.evidence.items;
  if (!items.length) return <Absent />;
  return (
    <div className="grid-2">
      {KINDS.map(({ kind, label }) => {
        const group = items.filter((it) => it.value.kind === kind);
        if (!group.length) return null;
        return (
          <div key={kind}>
            <h3 style={{ marginBottom: 10 }}>{label}</h3>
            <ul className="items">
              {group.map((it, i) => (
                <li key={i}>
                  <Value
                    label={it.value.label ?? label}
                    text={
                      <>
                        {it.value.label && <strong>{it.value.label} · </strong>}
                        {it.value.description}
                      </>
                    }
                    sources={it.sources}
                  />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

export function ResultView({ result }: { result: StructuredJudgment }) {
  const [tab, setTab] = useState<Tab>("overview");
  const counts: Partial<Record<Tab, number>> = {
    statutes: result.statutes.references.length,
    evidence: result.evidence.items.length,
    arguments: result.petitioner.arguments.length + result.respondent.arguments.length,
  };
  return (
    <div className="card flush">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {counts[t.id] !== undefined && <span className="muted"> · {counts[t.id]}</span>}
          </button>
        ))}
      </div>
      <div className="tab-body">
        {tab === "overview" && <Overview r={result} />}
        {tab === "facts" && <Facts r={result} />}
        {tab === "statutes" && <Statutes r={result} />}
        {tab === "arguments" && <Arguments r={result} />}
        {tab === "evidence" && <Evidence r={result} />}
      </div>
    </div>
  );
}
