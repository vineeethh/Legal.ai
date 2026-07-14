"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import type { DocumentSummary } from "@/lib/api";
import { DECISION_LABELS, STATUS_LABELS, formatDate } from "@/lib/labels";
import { cn, riseIn, staggerParent } from "@/components/ui";

/** One quiet voice per row: the filename leads; status is a small dot+word;
 *  confidence is a plain ledger numeral; decision is dot+word. No pill soup. */

const STATUS_DOT: Record<string, string> = {
  queued: "bg-faint",
  processing: "bg-accent",
  awaiting_review: "bg-warn",
  completed: "bg-success",
  rejected: "bg-danger",
  failed: "bg-danger",
  unknown: "bg-faint",
};

const DECISION_DOT: Record<string, string> = {
  auto_save: "bg-success",
  needs_review: "bg-warn",
  human_required: "bg-danger",
};

function StatusCell({ status }: { status: string }) {
  const live = status === "processing" || status === "queued";
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-muted">
      <span className={cn("h-[5px] w-[5px] rounded-full", STATUS_DOT[status] ?? "bg-faint", live && "live-dot")} />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function DecisionCell({ decision }: { decision: string | null | undefined }) {
  if (!decision) return <span className="text-[12px] text-faint">—</span>;
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-muted">
      <span className={cn("h-[5px] w-[5px] rounded-full", DECISION_DOT[decision] ?? "bg-faint")} />
      {DECISION_LABELS[decision] ?? decision}
    </span>
  );
}

export function DocumentsTable({ documents }: { documents: DocumentSummary[] }) {
  const router = useRouter();

  if (documents.length === 0) {
    return (
      <div>
        <div className="eyebrow flex items-baseline justify-between">
          <span>Docket</span>
        </div>
        <div className="rule-double mt-2" />
        <div className="px-2 py-14 text-center">
          <div className="mx-auto flex h-9 w-12 items-end justify-center gap-[3px] opacity-30">
            <span className="h-5 w-px bg-foreground" />
            <span className="h-8 w-px bg-foreground" />
            <span className="h-6 w-px bg-foreground" />
            <span className="h-9 w-px bg-foreground" />
            <span className="h-4 w-px bg-foreground" />
          </div>
          <p className="mt-4 font-serif text-[19px]">Nothing on the docket</p>
          <p className="mx-auto mt-1 max-w-sm text-[12.5px] leading-relaxed text-muted">
            Process your first judgment above — the extracted record lands here, every field
            carrying its verbatim source.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="eyebrow flex items-baseline justify-between">
        <span>Docket</span>
        <span className="tnum normal-case tracking-normal">
          {documents.length} document{documents.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="rule-double mt-2" />

      {/* column voice — desktop only */}
      <div className="hidden grid-cols-[minmax(0,1fr)_110px_72px_130px_18px] gap-x-5 border-b border-border py-2 sm:grid">
        {["Judgment", "Status", "Score", "Decision", ""].map((h, i) => (
          <span key={i} className={cn("text-[10.5px] uppercase tracking-[0.1em] text-faint", i === 2 && "text-right")}>
            {h}
          </span>
        ))}
      </div>

      <motion.ul variants={staggerParent} initial="hidden" animate="show">
        {documents.map((doc) => (
          <motion.li key={doc.id} variants={riseIn}>
            <button
              onClick={() => router.push(`/documents/${doc.id}`)}
              className="t-state group grid w-full grid-cols-[minmax(0,1fr)_18px] items-center gap-x-5 border-b border-border py-3.5 pl-1 pr-0 text-left transition-colors hover:bg-surface-2/60 sm:grid-cols-[minmax(0,1fr)_110px_72px_130px_18px]"
            >
              <span className="min-w-0">
                <span className="block truncate text-[13.5px] font-medium tracking-[-0.006em]">
                  {doc.filename}
                </span>
                <span className="tnum mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-faint">
                  {formatDate(doc.created_at ?? doc.uploaded_at)}
                  {doc.page_count ? <span>· {doc.page_count} pp</span> : null}
                  {/* compact status + decision, mobile only */}
                  <span className="flex items-center gap-2 sm:hidden">
                    <StatusCell status={doc.status} />
                    <DecisionCell decision={doc.decision} />
                  </span>
                </span>
              </span>
              <span className="hidden sm:block">
                <StatusCell status={doc.status} />
              </span>
              <span
                className={cn(
                  "tnum hidden text-right text-[13px] sm:block",
                  doc.confidence == null && "text-faint",
                )}
              >
                {doc.confidence == null ? "—" : doc.confidence.toFixed(3)}
              </span>
              <span className="hidden sm:block">
                <DecisionCell decision={doc.decision} />
              </span>
              <ArrowUpRight
                size={14}
                className="t-move justify-self-end text-faint opacity-0 transition-[opacity,transform] group-hover:translate-x-0.5 group-hover:opacity-100"
              />
            </button>
          </motion.li>
        ))}
      </motion.ul>
    </div>
  );
}
