"use client";

import { motion, useReducedMotion } from "framer-motion";
import { SIGNAL_LABELS } from "@/lib/labels";
import { AnimatedNumber, Card, DecisionBadge, cn } from "@/components/ui";

type Confidence = {
  score: number;
  decision: string;
  [signal: string]: number | string;
};

/** Confidence as a ledger, not a gauge: a ruled 0→1 scale with the two
 *  decision gates (0.80 review, 0.90 auto-save) drawn where they actually
 *  are, the document's score settling onto the scale, and each signal's
 *  weighted contribution itemized beneath — sums exactly to the score. */
export function ConfidencePanel({ confidence }: { confidence: Confidence }) {
  const reduced = useReducedMotion();
  const score = confidence.score;
  const tone = score >= 0.9 ? "text-success" : score >= 0.8 ? "text-warn" : "text-danger";
  const barTone = score >= 0.9 ? "bg-success" : score >= 0.8 ? "bg-warn" : "bg-danger";

  return (
    <Card className="overflow-hidden">
      <div className="eyebrow flex items-center justify-between border-b border-border px-5 py-2.5">
        <span>Confidence</span>
        <span className="normal-case tracking-normal">deterministic — no model grades itself</span>
      </div>

      <div className="px-5 pb-5 pt-4">
        <div className="flex items-end justify-between">
          <div className={cn("font-serif text-[44px] leading-none tracking-tight", tone)}>
            <AnimatedNumber value={score} decimals={3} />
          </div>
          <DecisionBadge decision={String(confidence.decision)} />
        </div>

        {/* the scale — gate labels sit under their ticks; the auto-save gate is
            end-anchored so nothing ever collides or clips */}
        <div className="relative mt-5 pb-7 pt-2">
          <div className="meter-ticks relative h-2.5 rounded-sm bg-surface-2">
            <motion.div
              initial={reduced ? false : { width: 0 }}
              animate={{ width: `${score * 100}%` }}
              transition={{ type: "spring", stiffness: 110, damping: 26 }}
              className={cn("absolute inset-y-0 left-0 rounded-sm opacity-80", barTone)}
            />
            {/* gate labels diverge from their ticks — 0.80 extends left, 0.90
                is anchored to the container's right edge — so they can never
                collide at any width */}
            <div className="absolute -top-1 bottom-0 left-[80%]">
              <span className="block h-[18px] w-px bg-foreground/55" />
              <span className="tnum absolute right-1 top-[22px] whitespace-nowrap text-[10px] text-faint">
                review 0.80
              </span>
            </div>
            <div className="absolute -top-1 bottom-0 left-[90%]">
              <span className="block h-[18px] w-px bg-foreground/55" />
            </div>
            <span className="tnum absolute right-0 top-[22px] whitespace-nowrap text-[10px] text-faint">
              0.90 auto-save
            </span>
          </div>
          <span className="tnum absolute bottom-0 left-0 text-[10px] text-faint">0</span>
        </div>

        {/* the ledger */}
        <div className="mt-3 border-t border-border">
          {Object.entries(SIGNAL_LABELS).map(([key, meta]) => {
            const value = typeof confidence[key] === "number" ? (confidence[key] as number) : 0;
            const contribution = value * meta.weight;
            return (
              <div
                key={key}
                className="grid grid-cols-[1fr_repeat(3,minmax(52px,auto))] items-baseline gap-3 border-b border-border py-2 text-[12px] last:border-b-0"
              >
                <span className="truncate text-muted">{meta.label}</span>
                <span className="tnum text-right text-faint">{value.toFixed(2)}</span>
                <span className="tnum text-right text-faint">× {meta.weight.toFixed(2)}</span>
                <span className="tnum text-right font-medium">{contribution.toFixed(3)}</span>
              </div>
            );
          })}
          <div className="grid grid-cols-[1fr_auto] items-baseline gap-3 pt-2 text-[12px]">
            <span className="eyebrow">Σ weighted</span>
            <span className={cn("tnum text-right font-semibold", tone)}>{score.toFixed(3)}</span>
          </div>
        </div>
      </div>
    </Card>
  );
}
