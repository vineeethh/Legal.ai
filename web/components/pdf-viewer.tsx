"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { ChevronLeft, ChevronRight } from "lucide-react";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { Card, Skeleton, cn } from "@/components/ui";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MAX_RENDERED_PAGES = 60; // judgments are typically short; hard-cap render cost

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const normalize = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();

/** Highlight the active provenance quote inside one PDF.js text item.
 *  Handles both directions: a short quote inside one item, and an item that is
 *  a fragment of a longer multi-item quote. Returns HTML for the text layer. */
function renderTextItem(str: string, quote: string | null): string {
  const escaped = escapeHtml(str);
  if (!quote) return escaped;
  const q = quote.replace(/\s+/g, " ").trim();
  if (!q) return escaped;

  const idx = str.toLowerCase().indexOf(q.toLowerCase());
  if (idx >= 0) {
    return (
      escapeHtml(str.slice(0, idx)) +
      `<mark>${escapeHtml(str.slice(idx, idx + q.length))}</mark>` +
      escapeHtml(str.slice(idx + q.length))
    );
  }
  const itemNorm = normalize(str);
  if (itemNorm.length > 3 && normalize(q).includes(itemNorm)) {
    return `<mark>${escaped}</mark>`;
  }
  return escaped;
}

export type Highlight = { page: number; quote: string } | null;

export function PdfViewer({
  url,
  highlight,
  onUnavailable,
}: {
  url: string;
  highlight: Highlight;
  onUnavailable?: () => void;
}) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [width, setWidth] = useState(560);
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});

  // Probe with HEAD before handing the URL to pdf.js — a missing file becomes
  // a quiet collapse instead of a console exception.
  useEffect(() => {
    let alive = true;
    fetch(url, { method: "HEAD" })
      .then((r) => {
        if (!alive) return;
        setAvailable(r.ok);
        if (!r.ok) onUnavailable?.();
      })
      .catch(() => {
        if (!alive) return;
        setAvailable(false);
        onUnavailable?.();
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // Track pane width so pages always fit it exactly.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.floor(w) - 2);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Scroll the highlighted page into view when a source chip is clicked.
  useEffect(() => {
    if (!highlight) return;
    const target = pageRefs.current[highlight.page];
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [highlight]);

  const file = useMemo(() => ({ url }), [url]);
  const pageCount = Math.min(numPages ?? 0, MAX_RENDERED_PAGES);

  if (available === null) return <Skeleton className="h-[60vh]" />;
  if (available === false) {
    return (
      <Card className="px-5 py-8 text-center text-[13px] text-muted">
        Source PDF not available for this document.
      </Card>
    );
  }

  return (
    <div ref={containerRef} className="flex h-full flex-col">
      {highlight ? (
        <div className="mb-3 rounded-lg border border-accent/30 bg-accent-soft px-4 py-2.5 text-xs">
          <span className="font-medium text-accent">Verbatim span · page {highlight.page}</span>
          <p className="mt-1 line-clamp-3 italic text-muted">“{highlight.quote}”</p>
        </div>
      ) : (
        <div className="mb-3 rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-xs text-muted">
          Click any <span className="font-medium">p.N</span> source chip in the record to highlight
          its verbatim span here.
        </div>
      )}
      <div className="pane-scroll flex-1 space-y-4 overflow-y-auto rounded-xl bg-surface-2/60 p-4">
        {error ? (
          <Card className="px-5 py-8 text-center text-sm text-muted">{error}</Card>
        ) : (
          <Document
            file={file}
            onLoadSuccess={(doc) => setNumPages(doc.numPages)}
            onLoadError={() => {
              setError("PDF unavailable — documents processed via the CLI keep their original filename.");
              onUnavailable?.();
            }}
            loading={<Skeleton className="h-96" />}
          >
            {Array.from({ length: pageCount }, (_, i) => {
              const pageNumber = i + 1;
              const isActive = highlight?.page === pageNumber;
              return (
                <div
                  key={pageNumber}
                  ref={(el) => {
                    pageRefs.current[pageNumber] = el;
                  }}
                  className={cn("relative mb-4 transition-opacity", isActive && "pdf-highlight")}
                >
                  <span
                    className={cn(
                      "tnum absolute -top-2 right-2 z-10 rounded px-1.5 py-0.5 text-[10px]",
                      isActive ? "bg-accent text-white" : "bg-surface-2 text-faint",
                    )}
                  >
                    {pageNumber}
                  </span>
                  <Page
                    pageNumber={pageNumber}
                    width={width - 32}
                    renderAnnotationLayer={false}
                    customTextRenderer={
                      isActive ? ({ str }) => renderTextItem(str, highlight?.quote ?? null) : undefined
                    }
                  />
                </div>
              );
            })}
          </Document>
        )}
      </div>
      {numPages ? (
        <div className="mt-2 flex items-center justify-center gap-2 text-xs text-faint">
          <ChevronLeft size={12} />
          {numPages} page{numPages === 1 ? "" : "s"}
          {numPages > MAX_RENDERED_PAGES ? ` (first ${MAX_RENDERED_PAGES} rendered)` : ""}
          <ChevronRight size={12} />
        </div>
      ) : null}
    </div>
  );
}
