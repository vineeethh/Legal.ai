import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { DecisionBadge } from "../components/Badges";
import { humanize, pct } from "../format";
import type { EvalReport, EvalReportSummary } from "../types";

function Tile({ k, v, hint }: { k: string; v: string; hint: string }) {
  return (
    <div className="tile" title={hint}>
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      <div className="muted small">{hint}</div>
    </div>
  );
}

function NoReports() {
  return (
    <div className="card">
      <h2>No evaluation reports yet</h2>
      <p className="muted">
        An evaluation compares the pipeline's output with judgments a person has labelled by hand. Label a few judgments
        in <code>evaluation/gold/</code> (copy <code>_template.json</code>), then run:
      </p>
      <pre className="block">{`# score predictions you already have (from pipeline.run --out)
python -m evaluation.run_eval

# or run the full pipeline on every labelled PDF first
docker compose run --rm app python -m evaluation.run_eval --run

# try it on the bundled synthetic example
python -m evaluation.run_eval --gold evaluation/examples/gold \\
  --predictions evaluation/examples/predictions --name example`}</pre>
    </div>
  );
}

export function EvaluationPage() {
  const [reports, setReports] = useState<EvalReportSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listReports()
      .then((list) => {
        setReports(list);
        if (list.length) setSelected(list[0].name);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    api
      .getReport(selected)
      .then(setReport)
      .catch((e: Error) => setError(e instanceof ApiError && e.status === 404 ? null : e.message));
  }, [selected]);

  const s = report?.summary;
  const overall = s?.scalar_overall;
  const r = s?.calibration.pearson_confidence_vs_doc_score;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Evaluation</h1>
          <p className="muted">How accurate the pipeline is against hand-labelled judgments.</p>
        </div>
        {reports && reports.length > 1 && (
          <select
            className="btn"
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            aria-label="Report"
          >
            {reports.map((rep) => (
              <option key={rep.name} value={rep.name}>
                {rep.name}
                {rep.synthetic ? " (synthetic)" : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <div className="callout bad" style={{ marginBottom: 16 }}>{error}</div>}
      {reports && reports.length === 0 && <NoReports />}
      {selected && !report && !error && <div className="muted">Loading report…</div>}

      {report && s && overall && (
        <div className="stack">
          {report.run.synthetic && (
            <div className="callout warn">
              <strong>Synthetic data.</strong> This report was produced from made-up examples to show how scoring works.
              It says nothing about real accuracy.
            </div>
          )}

          <div className="muted small">
            {report.run.documents_scored} of {report.run.documents_labelled} labelled judgments scored ·{" "}
            {report.run.llm_models.join(", ") || "unknown model"} · {new Date(report.run.created_at).toLocaleString()}
          </div>

          <div className="tiles">
            <Tile k="Field accuracy" v={pct(overall.accuracy)} hint="Labelled fields handled correctly, including correct ‘not found’." />
            <Tile k="Wrong when answering" v={pct(overall.error_rate_when_answered)} hint="Of the values it gave, how many were wrong or invented." />
            <Tile k="Abstained" v={pct(overall.abstention_rate)} hint="Returned nothing although the judgment had the value." />
            <Tile k="Statute F1" v={pct(s.statutes.extraction?.f1)} hint="Citations found vs. the labelled list." />
            <Tile k="Traceable values" v={pct(s.provenance.rate)} hint="Values that point back to a page and chunk." />
          </div>

          <div className="grid-2">
            <div className="card flush">
              <div style={{ padding: "16px 16px 0" }}>
                <h2>Single-value fields</h2>
              </div>
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th className="num">n</th>
                      <th className="num">Accuracy</th>
                      <th className="num">Wrong</th>
                      <th className="num">Abstained</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(s.scalar_fields).map(([name, f]) => (
                      <tr key={name}>
                        <td>{humanize(name)}</td>
                        <td className="num">{f.n}</td>
                        <td className="num">{pct(f.accuracy)}</td>
                        <td className="num">{pct(f.error_rate_when_answered)}</td>
                        <td className="num">{pct(f.abstention_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card flush">
              <div style={{ padding: "16px 16px 0" }}>
                <h2>List fields</h2>
              </div>
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th className="num">Precision</th>
                      <th className="num">Recall</th>
                      <th className="num">F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(s.list_fields).map(([name, f]) => (
                      <tr key={name}>
                        <td>
                          {humanize(name)}
                          <div className="muted small">
                            {f.tp} found · {f.fp} extra · {f.fn} missed
                          </div>
                        </td>
                        <td className="num">{pct(f.precision)}</td>
                        <td className="num">{pct(f.recall)}</td>
                        <td className="num">{pct(f.f1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Does the confidence score mean anything?</h2>
            <p className="muted small" style={{ marginTop: 0 }}>
              If the score works, documents it auto-saves should be more accurate than ones it sends to a person.
              Correlation between confidence and per-document score:{" "}
              <strong>{r === null || r === undefined ? "needs 3+ documents" : r.toFixed(2)}</strong>
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Decision</th>
                    <th className="num">Documents</th>
                    <th className="num">Mean document score</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(s.calibration.by_review_decision).map(([decision, row]) => (
                    <tr key={decision}>
                      <td>
                        <DecisionBadge decision={decision as never} />
                      </td>
                      <td className="num">{row.documents}</td>
                      <td className="num">{pct(row.mean_doc_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card flush">
            <div style={{ padding: "16px 16px 0" }}>
              <h2>Per judgment</h2>
            </div>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th className="num">Confidence</th>
                    <th>Decision</th>
                    <th className="num">Field accuracy</th>
                    <th className="num">Doc score</th>
                  </tr>
                </thead>
                <tbody>
                  {report.documents.map((d) => (
                    <tr key={d.case_id}>
                      <td className="mono">{d.case_id}</td>
                      <td className="num">{d.confidence_score.toFixed(3)}</td>
                      <td>
                        <DecisionBadge decision={d.review_decision} />
                      </td>
                      <td className="num">{pct(d.scalar_accuracy)}</td>
                      <td className="num">{pct(d.doc_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
