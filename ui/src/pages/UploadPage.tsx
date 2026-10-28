import { useRef, useState } from "react";

import { api } from "../api";
import { navigate } from "../router";
import type { Health } from "../types";

export function UploadPage({ health }: { health: Health | null }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  function pick(f: File | undefined) {
    setError(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    setFile(f);
  }

  async function start() {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const job = await api.upload(file, setProgress);
      navigate(`/documents/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
      setProgress(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>New analysis</h1>
          <p className="muted">Upload one court judgment. It is safety-checked before anything reads it.</p>
        </div>
      </div>

      <div className="stack" style={{ maxWidth: 720 }}>
        {health?.mode === "demo" && (
          <div className="callout info small">
            <strong>Demo mode.</strong> The API returns a synthetic result instead of running the real pipeline. Any PDF
            works. Put <code>review</code> in the file name to see the human-review pause, or <code>unsafe</code> to see
            a rejection.
          </div>
        )}

        <div
          className={`dropzone ${over ? "over" : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            pick(e.dataTransfer.files[0]);
          }}
        >
          <div className="big">📄</div>
          {file ? (
            <>
              <h2 style={{ margin: "12px 0 4px" }}>{file.name}</h2>
              <div className="muted small">{(file.size / 1024 / 1024).toFixed(2)} MB · click to choose another</div>
            </>
          ) : (
            <>
              <h2 style={{ margin: "12px 0 4px" }}>Drop a judgment PDF here</h2>
              <div className="muted small">or click to browse · up to 50 MB</div>
            </>
          )}
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </div>

        {progress !== null && (
          <div>
            <div className="muted small" style={{ marginBottom: 4 }}>
              Uploading… {Math.round(progress * 100)}%
            </div>
            <div className="bar">
              <span style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
          </div>
        )}

        {error && <div className="callout bad">{error}</div>}

        <div className="row">
          <button className="btn primary" disabled={!file || progress !== null} onClick={start}>
            Analyze judgment
          </button>
          <span className="muted small">You'll see each pipeline step live.</span>
        </div>
      </div>
    </>
  );
}
