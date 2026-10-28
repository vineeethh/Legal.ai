import { api } from "../api";
import { DecisionBadge, StatusBadge, scoreTone } from "../components/Badges";
import { relativeTime } from "../format";
import { navigate } from "../router";
import type { Job } from "../types";
import { usePolling } from "../usePolling";

const ACTIVE = new Set(["queued", "running", "awaiting_review"]);

export function DocumentsPage() {
  const { data: jobs, error, loading } = usePolling(api.listDocuments, {
    intervalMs: 2500,
    shouldPoll: (data: Job[] | null) => !data || data.some((j) => ACTIVE.has(j.status)),
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Judgments</h1>
          <p className="muted">Every uploaded judgment and where it is in the pipeline.</p>
        </div>
        <a className="btn primary" href="#/upload">
          New analysis
        </a>
      </div>

      {error && <div className="callout bad" style={{ marginBottom: 16 }}>Could not reach the API: {error.message}</div>}

      {loading && !jobs ? (
        <div className="muted">Loading…</div>
      ) : jobs && jobs.length === 0 ? (
        <div className="card empty">
          <div className="big">⚖️</div>
          <h2 style={{ margin: "12px 0 4px" }}>No judgments yet</h2>
          <p className="muted">Upload a court judgment PDF to extract a structured, source-cited record.</p>
          <a className="btn primary" href="#/upload">
            Upload a judgment
          </a>
        </div>
      ) : jobs ? (
        <div className="card flush">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th className="num">Confidence</th>
                  <th>Outcome</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className="clickable" onClick={() => navigate(`/documents/${job.id}`)}>
                    <td>
                      <a href={`#/documents/${job.id}`} onClick={(e) => e.stopPropagation()}>
                        {job.filename}
                      </a>
                      {job.demo && <span className="badge" style={{ marginLeft: 8 }}>demo</span>}
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="num" style={{ color: job.confidence_score !== null ? `var(--${scoreTone(job.confidence_score)})` : undefined }}>
                      {job.confidence_score !== null ? job.confidence_score.toFixed(3) : "—"}
                    </td>
                    <td>
                      <DecisionBadge decision={job.decision} />
                    </td>
                    <td className="muted small">{relativeTime(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}
