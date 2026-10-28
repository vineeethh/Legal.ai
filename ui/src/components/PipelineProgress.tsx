import { AGENT_LABEL } from "../format";
import type { AgentProgress, Job } from "../types";

type StepState = "done" | "active" | "pending" | "paused";

interface Step {
  title: string;
  detail: string;
  state: StepState;
}

const AGENT_STATUS_LABEL: Record<AgentProgress["status"], string> = {
  pending: "Waiting",
  running: "Extracting…",
  validating: "Validating…",
  retrying: "Retrying",
  done: "Done",
};

const AGENT_STATUS_TONE: Record<AgentProgress["status"], string> = {
  pending: "",
  running: "info",
  validating: "info",
  retrying: "warn",
  done: "ok",
};

/** Mirrors the LangGraph nodes in pipeline/graph.py. */
export function PipelineProgress({ job }: { job: Job }) {
  const done = new Set(job.progress.completed_nodes);
  const agents = Object.entries(job.progress.agents);
  const agentsDone = agents.every(([, a]) => a.status === "done");
  const paused = job.status === "awaiting_review";
  const finished = job.status === "completed";

  const raw: { title: string; detail: string; isDone: boolean }[] = [
    {
      title: "Safety check",
      detail: "pikepdf scans for JavaScript, auto-actions, embedded files, size and page limits.",
      isDone: done.has("pdf_safety_gate"),
    },
    {
      title: "Parse & chunk",
      detail: "Docling reads the layout (OCR only where needed); text is split by section and routed to agents.",
      isDone: done.has("parse_and_chunk"),
    },
    {
      title: "Prompt-injection screen",
      detail: "Regex scan for text aimed at the LLM. Flags only — legal text is never dropped.",
      isDone: done.has("injection_screen"),
    },
    {
      title: "Six agents extract in parallel",
      detail: "Each value must carry a verbatim quote; a validator checks it, and failing agents retry.",
      isDone: agentsDone && done.has("fan_in_gate"),
    },
    {
      title: "Verify statutes",
      detail: "Citations are looked up in the statute database, as in force on the decision date.",
      isDone: done.has("assemble"),
    },
    {
      title: "Confidence score",
      detail: "A weighted sum of five measured signals — computed in code, not by the LLM.",
      isDone: done.has("confidence"),
    },
  ];

  let activeFound = false;
  const steps: Step[] = raw.map((s) => {
    if (s.isDone || finished) return { ...s, state: "done" };
    if (!activeFound && job.status === "running") {
      activeFound = true;
      return { ...s, state: "active" };
    }
    return { ...s, state: "pending" };
  });
  if (paused || done.has("human_review") || job.review_decision) {
    steps.push({
      title: "Human review",
      detail: "Confidence was below 0.80, so the graph paused for a person to approve, reject or edit.",
      state: paused ? "paused" : "done",
    });
  }

  return (
    <ol className="steps">
      {steps.map((step, i) => (
        <li key={step.title} className={`step ${step.state}`}>
          <span className="step-icon">{step.state === "done" ? "✓" : step.state === "paused" ? "!" : i + 1}</span>
          <div>
            <div className="step-title">{step.title}</div>
            <div className="muted small">{step.detail}</div>
            {i === 3 && (
              <div className="agents">
                {agents.map(([name, a]) => (
                  <div key={name} className="agent">
                    <div className="name">{AGENT_LABEL[name] ?? name}</div>
                    <div className="row" style={{ marginTop: 4 }}>
                      <span className={`badge ${AGENT_STATUS_TONE[a.status]}`}>{AGENT_STATUS_LABEL[a.status]}</span>
                      {a.attempts > 1 && <span className="muted small">attempt {a.attempts}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
