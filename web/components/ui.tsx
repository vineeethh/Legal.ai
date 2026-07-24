"use client";

import { useEffect, useRef } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { motion, useMotionValue, useSpring, useReducedMotion } from "framer-motion";
import { STATUS_LABELS, DECISION_LABELS, VERIFICATION_LABELS } from "@/lib/labels";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* --------------------------- motion vocabulary --------------------------- */
/* One spring for entrances everywhere — consistent weight and momentum. */

export const springEnter = { type: "spring", stiffness: 420, damping: 34, mass: 0.9 } as const;

export const staggerParent = {
  hidden: {},
  show: { transition: { staggerChildren: 0.035 } },
};

export const riseIn = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: springEnter },
};

/** Numeric value that physically settles into place rather than snapping. */
export function AnimatedNumber({
  value,
  decimals = 0,
  className,
}: {
  value: number;
  decimals?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 120, damping: 26 });
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (reduced) {
      if (ref.current) ref.current.textContent = value.toFixed(decimals);
      return;
    }
    mv.set(value);
    const unsub = spring.on("change", (v) => {
      if (ref.current) ref.current.textContent = v.toFixed(decimals);
    });
    return unsub;
  }, [value, decimals, mv, spring, reduced]);

  return (
    <span ref={ref} className={cn("tnum", className)}>
      {(0).toFixed(decimals)}
    </span>
  );
}

/* ------------------------------ primitives ------------------------------- */

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface shadow-card", className)}>
      {children}
    </div>
  );
}

export function Button({
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button
      className={cn(
        "t-state inline-flex h-8.5 items-center justify-center gap-2 rounded-lg px-3.5 text-[13px] font-medium",
        "transition-[background-color,border-color,transform,box-shadow]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed disabled:opacity-45",
        "active:scale-[0.985]",
        variant === "primary" &&
          "bg-foreground text-background shadow-card hover:opacity-90",
        variant === "secondary" &&
          "border border-border-strong bg-surface text-foreground hover:border-foreground/30 hover:shadow-card",
        variant === "ghost" && "text-muted hover:bg-surface-2 hover:text-foreground",
        variant === "danger" &&
          "border border-danger/25 bg-danger-soft text-danger hover:border-danger/50",
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: "neutral" | "accent" | "success" | "warn" | "danger";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-[3px] text-[11px] font-medium leading-none",
        tone === "neutral" && "bg-surface-2 text-muted",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "success" && "bg-success-soft text-success",
        tone === "warn" && "bg-warn-soft text-warn",
        tone === "danger" && "bg-danger-soft text-danger",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("pulse-soft rounded-md bg-surface-2", className)} />;
}

/** Hairline-divided metric strip — structure from alignment, not boxes. */
export function MetricStrip({
  metrics,
}: {
  metrics: { label: string; value: React.ReactNode; hint?: string }[];
}) {
  return (
    <motion.div
      variants={staggerParent}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 divide-border rounded-xl border border-border bg-surface shadow-card sm:grid-cols-4 sm:divide-x"
    >
      {metrics.map((m) => (
        <motion.div key={m.label} variants={riseIn} className="px-5 py-4">
          <div className="eyebrow">{m.label}</div>
          <div className="mt-1.5 font-serif text-[28px] leading-none tracking-tight">{m.value}</div>
          {m.hint ? <div className="mt-1.5 truncate text-[11px] text-faint">{m.hint}</div> : null}
        </motion.div>
      ))}
    </motion.div>
  );
}

/* legacy alias kept for compatibility */
export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return <MetricStrip metrics={[{ label, value, hint }]} />;
}

/* --------------------------- semantic badges ---------------------------- */

const STATUS_TONE: Record<string, "neutral" | "accent" | "success" | "warn" | "danger"> = {
  queued: "neutral",
  processing: "accent",
  awaiting_review: "warn",
  completed: "success",
  rejected: "danger",
  failed: "danger",
  unknown: "neutral",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  const live = status === "processing" || status === "queued";
  return (
    <Badge tone={tone}>
      <span
        className={cn("inline-block h-1.5 w-1.5 rounded-full bg-current", live && "live-dot")}
      />
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

const DECISION_TONE: Record<string, "success" | "warn" | "danger"> = {
  auto_save: "success",
  needs_review: "warn",
  human_required: "danger",
};

export function DecisionBadge({ decision }: { decision: string | null | undefined }) {
  if (!decision) return <span className="text-faint">—</span>;
  return <Badge tone={DECISION_TONE[decision] ?? "neutral"}>{DECISION_LABELS[decision] ?? decision}</Badge>;
}

const VERIFICATION_TONE: Record<string, "success" | "warn" | "danger" | "neutral"> = {
  verified: "success",
  not_found: "warn",
  mismatch: "danger",
  skipped: "neutral",
};

export function VerificationBadge({ status }: { status: string }) {
  return (
    <Badge tone={VERIFICATION_TONE[status] ?? "neutral"}>{VERIFICATION_LABELS[status] ?? status}</Badge>
  );
}

export function ConfidenceValue({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-faint">—</span>;
  const tone = value >= 0.9 ? "text-success" : value >= 0.8 ? "text-warn" : "text-danger";
  return <span className={cn("tnum font-medium", tone)}>{value.toFixed(3)}</span>;
}
