import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "../api";
import type { SourceRef } from "../types";

interface OpenSource {
  label: string;
  value: string;
  source: SourceRef;
}

const SourceContext = createContext<(s: OpenSource) => void>(() => {});

/** Wrap a result view; any <SourceChips> inside opens the drawer for this document. */
export function SourceProvider({ documentId, children }: { documentId: string; children: ReactNode }) {
  const [open, setOpen] = useState<OpenSource | null>(null);
  return (
    <SourceContext.Provider value={setOpen}>
      {children}
      {open && <SourceDrawer documentId={documentId} open={open} onClose={() => setOpen(null)} />}
    </SourceContext.Provider>
  );
}

export function SourceChips({ sources, label, value }: { sources: SourceRef[]; label: string; value: string }) {
  const openSource = useContext(SourceContext);
  if (!sources.length) return null;
  return (
    <>
      {sources.map((source, i) => (
        <button
          key={i}
          type="button"
          className="src"
          title={`“${source.quote}”`}
          onClick={() => openSource({ label, value, source })}
        >
          p.{source.page}
        </button>
      ))}
    </>
  );
}

// The PDF blob is fetched once per document and reused by every drawer opening.
const pdfCache = new Map<string, Promise<string>>();

function SourceDrawer({ documentId, open, onClose }: { documentId: string; open: OpenSource; onClose: () => void }) {
  const { label, value, source } = open;
  const [showPdf, setShowPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!showPdf) return;
    if (!pdfCache.has(documentId)) pdfCache.set(documentId, api.pdfUrl(documentId));
    pdfCache
      .get(documentId)!
      .then(setPdfUrl)
      .catch((e: Error) => {
        pdfCache.delete(documentId);
        setPdfError(e.message);
      });
  }, [showPdf, documentId]);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Source">
        <div className="drawer-head">
          <h2>Source · {label}</h2>
          <span className="spacer" />
          <button className="btn small" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="drawer-body">
          <div>
            <div className="muted small">Extracted value</div>
            <div style={{ fontWeight: 600 }}>{value}</div>
          </div>
          <div>
            <div className="muted small" style={{ marginBottom: 6 }}>
              Verbatim quote from the judgment — the validator checked that this text exists in the source chunk
            </div>
            <blockquote className="quote">“{source.quote}”</blockquote>
          </div>
          <dl className="fields">
            <dt>Page</dt>
            <dd>{source.page}</dd>
            <dt>Section</dt>
            <dd>{source.section_path ?? <span className="absent">—</span>}</dd>
            <dt>Chunk</dt>
            <dd className="mono">{source.chunk_id ?? <span className="absent">—</span>}</dd>
          </dl>
          {!showPdf ? (
            <button className="btn" onClick={() => setShowPdf(true)}>
              Open the PDF at page {source.page}
            </button>
          ) : pdfError ? (
            <div className="callout bad">{pdfError}</div>
          ) : pdfUrl ? (
            <iframe className="pdf-frame" title="Judgment PDF" src={`${pdfUrl}#page=${source.page}`} />
          ) : (
            <div className="muted">Loading PDF…</div>
          )}
        </div>
      </aside>
    </>
  );
}
