"use client";

import { motion } from "framer-motion";
import { Check, CircleDashed } from "lucide-react";
import type { JobEvent } from "@/lib/api";
import { Card, cn } from "@/components/ui";

const AGENTS = ["metadata", "facts", "statute", "petitioner", "respondent", "evidence"] as const;

const AGENT_LABELS: Record<string, string> = {
  metadata: "Metadata",
  facts: "Facts",
  statute: "Statutes",
  petitioner: "Petitioner",
  respondent: "Respondent",
  evidence: "Evidence",
};

type LaneState = {
  status: "pending" | "extracting" | "validating" | "done";
  attempts: number;
};

type StageStatus = "pending" | "active" | "done";

/** Derive per-stage and per-agent state from the raw node-event stream. The
 *  graph's own topology (intake → fan-out → barrier → verify → score → decide)
 *  is the hierarchy the user should see — not a flat log. */
function derive(events: JobEvent[], terminal: boolean) {
  const nodes = events.filter((e) => e.type === "node" && e.node).map((e) => e.node as string);
  const seen = new Set(nodes);
  const last = nodes[nodes.length - 1];

  const intakeDone = seen.has("injection_screen");
  const barrierPassed = seen.has("assemble");
  const scored = seen.has("confidence");
  const decisionEvent = [...events].reverse().find(
    (e) => e.type === "status" && ["awaiting_review", "completed", "rejected", "failed"].includes(e.status ?? ""),
  );

  const lanes: Record<string, LaneState> = {};
  for (const agent of AGENTS) {
    const attempts = nodes.filter((n) => n === agent).length;
    const validations = nodes.filter((n) => n === `${agent}_confidence`).length;
    let status: LaneState["status"] = "pending";
    if (barrierPassed || terminal) status = attempts > 0 || terminal ? "done" : "pending";
    else if (last === agent) status = "extracting";
    else if (last === `${agent}_confidence`) status = "validating";
    else if (attempts > 0 && validations >= attempts) status = "done";
    else if (attempts > 0) status = "extracting";
    lanes[agent] = { status, attempts };
  }

  const stages: { id: string; label: string; status: StageStatus; detail?: string }[] = [
    {
      id: "intake",
      label: "Intake",
      status: intakeDone ? "done" : nodes.length > 0 ? "active" : "pending",
      detail: "safety scan · parse · injection screen",
    },
    {
      id: "extraction",
      label: "Extraction & validation",
      status: barrierPassed ? "done" : intakeDone ? "active" : "pending",
      detail: "6 isolated agents · span-grounded validator",
    },
    {
      id: "verification",
      label: "Statute verification",
      status: scored ? "done" : seen.has("assemble") && last === "assemble" ? "active" : barrierPassed ? "done" : "pending",
      detail: "exact KB lookup, as of decision date",
    },
    {
      id: "scoring",
      label: "Confidence & decision",
      status: decisionEvent ? "done" : scored || last === "confidence" ? "active" : "pending",
      detail: "5 deterministic signals",
    },
  ];

  return { lanes, stages };
}

function LaneDot({ state }: { state: LaneState }) {
  if (state.status === "done") return <Check size={12} strokeWidth={2.5} className="text-success" />;
  if (state.status === "pending") return <CircleDashed size={12} className="text-faint" />;
  return <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-accent text-accent" />;
}

export function ProcessingTimeline({ events, active }: { events: JobEvent[]; active: boolean }) {
  const { lanes, stages } = derive(events, !active);

  return (
    <Card className="overflow-hidden">
      <div className="eyebrow flex items-center justify-between border-b border-border px-5 py-2.5">
        <span>Pipeline</span>
        {active ? (
          <span className="flex items-center gap-2 normal-case tracking-normal text-accent">
            <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-accent" />
            live
          </span>
        ) : (
          <span className="normal-case tracking-normal text-faint">finished</span>
        )}
      </div>

      <div className="px-5 py-4">
        {stages.map((stage, i) => (
          <div key={stage.id} className="relative flex gap-3.5 pb-5 last:pb-0">
            {i < stages.length - 1 ? (
              <span
                className={cn(
                  "t-move absolute left-[9px] top-5 h-full w-px transition-colors",
                  stage.status === "done" ? "bg-success/40" : "bg-border",
                )}
              />
            ) : null}
            <span
              className={cn(
                "z-10 mt-0.5 flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full border bg-surface",
                stage.status === "done" && "border-success/50 text-success",
                stage.status === "active" && "border-accent text-accent",
                stage.status === "pending" && "border-border-strong text-faint",
              )}
            >
              {stage.status === "done" ? (
                <Check size={10} strokeWidth={3} />
              ) : stage.status === "active" ? (
                <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
              ) : (
                <span className="h-1 w-1 rounded-full bg-current" />
              )}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <span
                  className={cn(
                    "text-[13px] font-medium",
                    stage.status === "pending" && "text-faint",
                  )}
                >
                  {stage.label}
                </span>
                <span className="truncate text-[11px] text-faint">{stage.detail}</span>
              </div>

              {stage.id === "extraction" && stage.status !== "pending" ? (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  transition={{ type: "spring", stiffness: 380, damping: 34 }}
                  className="mt-2.5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3"
                >
                  {AGENTS.map((agent) => {
                    const lane = lanes[agent];
                    return (
                      <div
                        key={agent}
                        className={cn(
                          "flex items-center justify-between gap-2 bg-surface px-3 py-2",
                          lane.status === "pending" && "opacity-55",
                        )}
                      >
                        <span className="flex items-center gap-2 text-[12px]">
                          <LaneDot state={lane} />
                          {AGENT_LABELS[agent]}
                        </span>
                        <span className="tnum text-[10px] text-faint">
                          {lane.status === "validating"
                            ? "validating"
                            : lane.status === "extracting"
                              ? lane.attempts > 1
                                ? `retry ${lane.attempts - 1}`
                                : "extracting"
                              : lane.attempts > 1
                                ? `${lane.attempts} attempts`
                                : ""}
                        </span>
                      </div>
                    );
                  })}
                </motion.div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
