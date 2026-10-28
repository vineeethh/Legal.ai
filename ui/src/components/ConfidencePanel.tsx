import { pct } from "../format";
import type { ConfidenceBreakdown } from "../types";
import { DecisionBadge, scoreTone } from "./Badges";

// Same weights as schemas/confidence.py (ConfidenceWeights).
const SIGNALS: { key: keyof ConfidenceBreakdown; label: string; weight: number; help: string }[] = [
  {
    key: "validation_pass_rate",
    label: "Validation pass rate",
    weight: 0.35,
    help: "Share of extracted values whose quote was found and supports the value.",
  },
  {
    key: "statute_verification_rate",
    label: "Statutes verified",
    weight: 0.2,
    help: "Share of cited sections found in the statute database.",
  },
  {
    key: "provenance_coverage",
    label: "Provenance coverage",
    weight: 0.2,
    help: "Share of values that point back to a page and chunk.",
  },
  {
    key: "schema_completeness",
    label: "Core fields present",
    weight: 0.15,
    help: "Court, decision date and case number found.",
  },
  {
    key: "cross_agent_consistency",
    label: "Consistency",
    weight: 0.1,
    help: "No timeline event dated after the judgment.",
  },
];

export function ConfidencePanel({ confidence }: { confidence: ConfidenceBreakdown }) {
  const tone = scoreTone(confidence.score);
  return (
    <div className="card">
      <div className="row" style={{ alignItems: "flex-end", marginBottom: 16 }}>
        <div>
          <div className="muted small">Confidence score</div>
          <div className="score" style={{ color: `var(--${tone})` }}>
            {confidence.score.toFixed(3)}
          </div>
        </div>
        <span className="spacer" />
        <DecisionBadge decision={confidence.decision} />
      </div>
      {SIGNALS.map((s) => {
        const value = confidence[s.key] as number;
        return (
          <div key={s.key} className="signal" title={s.help}>
            <div>
              <div className="label">{s.label}</div>
              <div className="weight">
                weight {s.weight.toFixed(2)} · adds {(value * s.weight).toFixed(3)}
              </div>
            </div>
            <div className={`bar ${scoreTone(value)}`}>
              <span style={{ width: `${Math.round(value * 100)}%` }} />
            </div>
            <div className="num small" style={{ textAlign: "right" }}>
              {pct(value, 0)}
            </div>
          </div>
        );
      })}
      <p className="muted small" style={{ marginBottom: 0 }}>
        ≥ 0.90 saves automatically · 0.80–0.90 saves with a review flag · below 0.80 pauses for a person. Computed in
        code from the signals above — the LLM never scores itself.
      </p>
    </div>
  );
}
