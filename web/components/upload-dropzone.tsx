"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { FileUp, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/components/ui";

export function UploadDropzone() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reduced = useReducedMotion();

  const handleFile = useCallback(
    async (file: File | undefined | null) => {
      if (!file || busy) return;
      setError(null);
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Only PDF judgments are accepted.");
        return;
      }
      setBusy(true);
      try {
        const job = await api.upload(file);
        router.push(`/documents/${job.id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed.");
        setBusy(false);
      }
    },
    [busy, router],
  );

  // "U" opens the picker when no field is focused — quiet keyboard craft.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (e.key.toLowerCase() === "u" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName)) return;
        inputRef.current?.click();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div>
      <motion.label
        animate={
          reduced
            ? undefined
            : { scale: dragOver ? 1.008 : 1, y: dragOver ? -1 : 0 }
        }
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "t-move group flex cursor-pointer items-center justify-between gap-6 rounded-xl border px-6 py-5",
          "transition-[border-color,background-color,box-shadow]",
          dragOver
            ? "border-accent bg-accent-soft shadow-lift"
            : "border-border bg-surface shadow-card hover:border-border-strong hover:shadow-lift",
          busy && "pointer-events-none opacity-60",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          disabled={busy}
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <div className="flex items-center gap-4">
          <span
            className={cn(
              "t-move flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-surface-2 text-muted",
              "transition-[color,border-color,transform] group-hover:-translate-y-0.5 group-hover:text-accent",
              dragOver && "-translate-y-0.5 border-accent/40 text-accent",
            )}
          >
            <FileUp size={17} strokeWidth={1.8} />
          </span>
          <div>
            <div className="text-[13.5px] font-medium">
              {busy ? "Uploading…" : dragOver ? "Release to begin" : "Process a judgment"}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
              <ShieldCheck size={12} className="text-success" />
              Structurally scanned before any model reads a byte
            </div>
          </div>
        </div>
        <span className="hidden items-center gap-1.5 text-[11px] text-faint sm:flex">
          drop a PDF or press
          <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-sans text-[10px] font-medium text-muted">
            U
          </kbd>
        </span>
      </motion.label>
      {error ? <p className="mt-2 text-[13px] text-danger">{error}</p> : null}
    </div>
  );
}
