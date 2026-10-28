import { useEffect, useState } from "react";

import { api } from "../api";
import { StatusBadge } from "../components/Badges";
import { ConfidencePanel } from "../components/ConfidencePanel";
import { PipelineProgress } from "../components/PipelineProgress";
import { ResultView } from "../components/ResultView";
import { ReviewPanel } from "../components/ReviewPanel";
import { SourceProvider } from "../components/Source";
import { duration, relativeTime } from "../format";
import type { Job, ReviewPayload, StructuredJudgment } from "../types";
import { usePolling } from "../usePolling";

const TERMINAL = new Set(["completed", "rejected", "failed"]);

export function DocumentPage({ id }: { id: string }) {
  const { data: job, error, reload } = usePolling(() => api.getDocument(id), {
    intervalMs: 1000,
    shouldPoll: (j: Job | null) => !j || (!TERMINAL.has(j.status) && j.status !== "awaiting_review"),
    deps: [id],
  });
  const [result, setResult] = useState<StructuredJudgment | null>(null);
  const [review, setReview] = useState<ReviewPayload | null>(null);
  // Set once a decision is sent: the next poll may still say "awaiting_review"
  // for a moment, and the review payload no longer exists by then.
  const [reviewSent, setReviewSent] = useState(false);

  useEffect(() => {
    setResult(null);
    setReview(null);
    setReviewSent(false);
  }, [id]);

  useEffect(() => {
    if (job?.status === "completed" && !result) api.getResult(id).then(setResult).catch(() => {});
    if (job?.status === "awaiting_review" && !review && !reviewSent) api.getReview(id).then(setReview).catch(() => {});
  }, [job?.status, id, result, review, reviewSent]);

  if (error && !job) {
    return <div className="callout bad">{error.message}</div>;
  }
  if (!job) return <div className="muted">Loading…</div>;

  function afterReview() {
    setReviewSent(true);
    setReview(null);
    // The graph resumes; poll again until it finishes.
    const poll = async () => {
      const next = await reload();
      if (next && !TERMINAL.has(next.status)) window.setTimeout(poll, 1000);
    };
    poll();
  }

  function downloadJson() {
    if (!result || !job) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = job.filename.replace(/\.pdf$/i, "") + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const showProgress = job.status === "queued" || job.status === "running" || job.status === "awaiting_review";

  return (
    <SourceProvider documentId={id}>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="muted small">
            <a href="#/documents">Judgments</a> /
          </div>
          <h1 style={{ overflowWrap: "anywhere" }}>{job.filename}</h1>
          <div className="row muted small" style={{ marginTop: 6 }}>
            <StatusBadge status={job.status} />
            <span>uploaded {relativeTime(job.created_at)}</span>
            {job.started_at && <span>· ran {duration(job.started_at, job.completed_at)}</span>}
            {job.demo && <span className="badge">demo result</span>}
          </div>
        </div>
        {result && (
          <button className="btn" onClick={downloadJson}>
            Download JSON
          </button>
        )}
      </div>

      <div className="stack">
        {job.status === "rejected" && (
          <div className="callout bad">
            <h2 style={{ marginBottom: 6 }}>Rejected by the safety check</h2>
            <p style={{ margin: "0 0 6px" }}>The PDF was refused before any parser or model read it:</p>
            <ul style={{ margin: 0 }}>
              {job.rejection_reasons.map((r) => (
                <li key={r} className="mono">
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {job.status === "failed" && (
          <div className="callout bad">
            <h2 style={{ marginBottom: 6 }}>The run failed</h2>
            <pre className="block">{job.error}</pre>
          </div>
        )}

        {job.status === "awaiting_review" && review && (
          <ReviewPanel documentId={id} payload={review} onDone={afterReview} />
        )}

        {showProgress && (
          <div className="card">
            <h2>Pipeline</h2>
            <PipelineProgress job={job} />
          </div>
        )}

        {job.status === "awaiting_review" && review && (
          <>
            <h2 style={{ marginTop: 8 }}>What the pipeline extracted</h2>
            <div className="split">
              <ConfidencePanel confidence={review.result_preview.confidence} />
              <ResultView result={review.result_preview} />
            </div>
          </>
        )}

        {result && (
          <>
            {job.review_decision && (
              <div className="callout info small">
                A reviewer chose <strong>{job.review_decision.action}</strong> before this record was saved.
              </div>
            )}
            <div className="split">
              <div className="stack" style={{ alignContent: "start" }}>
                <ConfidencePanel confidence={result.confidence} />
                <div className="card small">
                  <h2>Run details</h2>
                  <dl className="fields">
                    <dt>Model</dt>
                    <dd className="mono">{result.processing.llm_model}</dd>
                    <dt>Retries</dt>
                    <dd>
                      {Object.entries(result.processing.retry_counts).filter(([, n]) => n > 0).length
                        ? Object.entries(result.processing.retry_counts)
                            .filter(([, n]) => n > 0)
                            .map(([a, n]) => `${a} ×${n}`)
                            .join(", ")
                        : "none"}
                    </dd>
                    <dt>Run id</dt>
                    <dd className="mono" style={{ overflowWrap: "anywhere" }}>
                      {job.processing_run_id ?? job.id}
                    </dd>
                  </dl>
                </div>
              </div>
              <ResultView result={result} />
            </div>
          </>
        )}
      </div>
    </SourceProvider>
  );
}
