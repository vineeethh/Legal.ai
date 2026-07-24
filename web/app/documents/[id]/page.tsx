"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, ShieldX } from "lucide-react";
import { api, type DocumentSummary, type JobEvent, type ReviewPayload } from "@/lib/api";
import { formatDate } from "@/lib/labels";
import { Card, ConfidenceValue, Skeleton, StatusBadge, cn } from "@/components/ui";
import { ProcessingTimeline } from "@/components/processing-timeline";
import { ConfidencePanel } from "@/components/confidence-panel";
import { RecordView } from "@/components/record-view";
import { ReviewBanner } from "@/components/review-banner";
import { AuditTrail } from "@/components/audit-trail";
import type { Highlight } from "@/components/pdf-viewer";

// PDF.js touches DOM APIs at import time — client-only.
const PdfViewer = dynamic(() => import("@/components/pdf-viewer").then((m) => m.PdfViewer), {
  ssr: false,
  loading: () => <Skeleton className="h-[70vh]" />,
});

const ACTIVE_STATUSES = new Set(["queued", "processing", "awaiting_review"]);

type Tab = "record" | "source" | "audit";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentSummary | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [reviewPayload, setReviewPayload] = useState<ReviewPayload | null>(null);
  const [highlight, setHighlight] = useState<Highlight>(null);
  const [tab, setTab] = useState<Tab>("record");
  const [notFound, setNotFound] = useState(false);
  const [pdfOk, setPdfOk] = useState(true);
  const esRef = useRef<EventSource | null>(null);

  const refreshDoc = useCallback(async () => {
    try {
      const d = await api.getDocument(id);
      setDoc(d);
      if (d.has_pdf === false) setPdfOk(false); // never even request a missing file
      if (d.review_payload) setReviewPayload(d.review_payload);
      if (d.status === "completed" || d.status === "unknown") {
        api.getResult(id).then(setResult).catch(() => {});
      }
      return d;
    } catch {
      setNotFound(true);
      return null;
    }
  }, [id]);

  useEffect(() => {
    let alive = true;
    let poll: ReturnType<typeof setInterval> | null = null;

    refreshDoc().then((d) => {
      if (!alive || !d) return;
      // Live events exist only for jobs this server ran (source === "memory");
      // opening an EventSource against a db-era document would just 404.
      if (ACTIVE_STATUSES.has(d.status) && d.source !== "memory") {
        poll = setInterval(refreshDoc, 4000);
        return;
      }
      if (ACTIVE_STATUSES.has(d.status)) {
        const es = new EventSource(api.eventsUrl(id));
        esRef.current = es;
        es.onmessage = (msg) => {
          const event: JobEvent = JSON.parse(msg.data);
          setEvents((prev) => [...prev, event]);
          if (event.type === "status") {
            if (event.status === "awaiting_review" && event.payload) {
              setReviewPayload(event.payload);
            }
            refreshDoc();
            if (event.status && !ACTIVE_STATUSES.has(event.status)) es.close();
          }
        };
        es.onerror = () => {
          es.close();
          if (!poll) poll = setInterval(refreshDoc, 4000);
        };
      }
    });

    return () => {
      alive = false;
      esRef.current?.close();
      if (poll) clearInterval(poll);
    };
  }, [id, refreshDoc]);

  const onSource = useCallback((page: number, quote: string) => {
    // On wide screens the viewer sits beside the record; below xl it lives in
    // the Source tab, so a chip click navigates there — causality preserved.
    const wide = typeof window !== "undefined" && window.matchMedia("(min-width: 1280px)").matches;
    setTab(wide ? "record" : "source");
    setHighlight({ page, quote });
  }, []);

  if (notFound) {
    return (
      <Card className="px-8 py-14 text-center">
        <p className="font-serif text-xl">Document not found</p>
        <Link href="/" className="mt-2 inline-block text-[13px] text-accent hover:underline">
          ← Back to the docket
        </Link>
      </Card>
    );
  }

  if (!doc) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-40" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const isActive = ACTIVE_STATUSES.has(doc.status);
  const confidence = result?.confidence;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 380, damping: 34 }}
      className="space-y-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0">
          <Link
            href="/"
            className="t-state mb-1.5 inline-flex items-center gap-1 text-[11px] text-faint transition-colors hover:text-accent"
          >
            <ArrowLeft size={11} /> docket
          </Link>
          <h1 className="break-words font-serif text-[26px] leading-tight tracking-tight">{doc.filename}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-muted">
            <StatusBadge status={doc.status} />
            {doc.page_count ? <span className="tnum">{doc.page_count} pp</span> : null}
            <span className="tnum">{formatDate(doc.created_at ?? doc.uploaded_at)}</span>
            {doc.confidence != null ? <ConfidenceValue value={doc.confidence} /> : null}
          </div>
        </div>
        {result ? (
          <div className="flex rounded-lg border border-border bg-surface-2 p-0.5">
            {(["record", "source", "audit"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "t-state rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors",
                  // the Source tab only exists below xl — wider screens keep
                  // the permanent split view
                  t === "source" && (!pdfOk ? "hidden" : "xl:hidden"),
                  tab === t ? "bg-surface text-foreground shadow-card" : "text-muted hover:text-foreground",
                )}
              >
                {t === "record" ? "Record" : t === "source" ? "Source" : "Audit trail"}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {doc.status === "rejected" ? (
        <Card className="border-danger/25 px-6 py-5">
          <div className="flex items-start gap-3">
            <ShieldX size={17} className="mt-0.5 text-danger" />
            <div>
              <h3 className="font-serif text-lg">Rejected by the structural safety scan</h3>
              <p className="mt-1 text-[13px] text-muted">
                This file was never handed to a parser or a model.{" "}
                <span className="font-mono text-[11.5px]">{doc.error}</span>
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      {doc.status === "failed" ? (
        <Card className="border-danger/25 px-6 py-5">
          <h3 className="font-serif text-lg">Run failed</h3>
          <p className="mt-1 font-mono text-[11.5px] text-muted">{doc.error}</p>
        </Card>
      ) : null}

      {doc.status === "awaiting_review" ? (
        <ReviewBanner documentId={doc.id} payload={reviewPayload} onDecided={refreshDoc} />
      ) : null}

      {isActive || (events.length > 0 && !result) ? (
        <div className={cn("grid gap-5", confidence ? "lg:grid-cols-[1fr_360px]" : "max-w-xl")}>
          {confidence ? <ConfidencePanel confidence={confidence} /> : null}
          <ProcessingTimeline events={events} active={doc.status === "processing" || doc.status === "queued"} />
        </div>
      ) : null}

      {result && tab === "audit" ? (
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <AuditTrail documentId={doc.id} processing={result.processing ?? null} langfuseSessionId={doc.id} />
          <ConfidencePanel confidence={confidence} />
        </div>
      ) : null}

      {/* Below xl the Source tab hosts the viewer; xl+ keeps the split view
          (the "source" tab state simply behaves as "record" there). */}
      {result && tab === "source" && pdfOk ? (
        <div className="h-[75vh] min-w-0 xl:hidden">
          <PdfViewer url={api.pdfUrl(doc.id)} highlight={highlight} onUnavailable={() => setPdfOk(false)} />
        </div>
      ) : null}

      {result && tab !== "audit" ? (
        <div
          className={cn(
            "items-start gap-6",
            tab === "source" ? "hidden xl:grid" : "grid",
            pdfOk ? "xl:grid-cols-[minmax(0,1fr)_minmax(0,44%)]" : "mx-auto max-w-3xl",
          )}
        >
          <div className="min-w-0 space-y-5">
            {!isActive && events.length === 0 && confidence ? (
              <ConfidencePanel confidence={confidence} />
            ) : null}
            <RecordView result={result} onSource={onSource} />
          </div>
          {pdfOk ? (
            <div className="sticky top-[72px] hidden h-[calc(100vh-96px)] min-w-0 xl:block">
              <PdfViewer url={api.pdfUrl(doc.id)} highlight={highlight} onUnavailable={() => setPdfOk(false)} />
            </div>
          ) : null}
        </div>
      ) : null}

      {!result && doc.status === "completed" ? <Skeleton className="h-96" /> : null}
    </motion.div>
  );
}
