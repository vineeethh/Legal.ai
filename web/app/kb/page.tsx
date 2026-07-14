"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { api, type KbSection, type KbStats } from "@/lib/api";
import { AnimatedNumber, Badge, Card, Skeleton, cn, riseIn, staggerParent } from "@/components/ui";

/** The verification source of truth, browsable: which acts are loaded, which
 *  sections exist, and what the canonical text says — the same rows the
 *  pipeline's Tier-1 lookup runs against. */
export default function KnowledgeBasePage() {
  const [stats, setStats] = useState<KbStats | null>(null);
  const [query, setQuery] = useState("");
  const [act, setAct] = useState<string | null>(null);
  const [results, setResults] = useState<KbSection[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.kbStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    debounce.current = setTimeout(() => {
      api
        .kbSearch(q, act ?? undefined)
        .then((r) => setResults(r))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [query, act]);

  return (
    <div className="space-y-8">
      <div className="max-w-2xl">
        <h1 className="font-serif text-[34px] leading-[1.08] sm:text-[44px]">The statute book</h1>
        <div className="rule-double mt-5" />
        <p className="mt-4 text-[13px] leading-relaxed text-muted">
          Every citation a judgment makes is verified against these exact rows — the act actually
          cited, in force on the decision date. Postgres is authoritative; embeddings only assist,
          they never issue a verdict.
        </p>
      </div>

      {/* coverage strip */}
      {stats ? (
        <motion.div
          variants={staggerParent}
          initial="hidden"
          animate="show"
          className="flex flex-wrap items-stretch divide-x divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-card"
        >
          {stats.acts.map((a) => (
            <motion.button
              key={a.act_version}
              variants={riseIn}
              onClick={() => setAct(act === a.act_version ? null : a.act_version)}
              className={cn(
                "t-state flex-1 px-5 py-4 text-left transition-colors",
                act === a.act_version ? "bg-accent-soft" : "hover:bg-surface-2",
              )}
            >
              <div className="eyebrow">{a.act_version}</div>
              <div className="mt-1 font-serif text-[26px] leading-none">
                <AnimatedNumber value={a.sections} />
                <span className="ml-1.5 font-sans text-[11px] text-faint">sections</span>
              </div>
            </motion.button>
          ))}
          <motion.div variants={riseIn} className="flex-1 px-5 py-4">
            <div className="eyebrow">Crosswalk</div>
            <div className="mt-1 font-serif text-[26px] leading-none">
              <AnimatedNumber value={stats.crosswalk_mappings} />
              <span className="ml-1.5 font-sans text-[11px] text-faint">old → new mappings</span>
            </div>
          </motion.div>
        </motion.div>
      ) : (
        <Skeleton className="h-[86px]" />
      )}

      {/* search */}
      <div>
        <div className="relative">
          <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search section number, title, or text${act ? ` in ${act}` : " across all acts"}…`}
            className={cn(
              "t-state h-11 w-full rounded-xl border border-border bg-surface pl-11 pr-4 text-[13.5px] shadow-card",
              "transition-[border-color,box-shadow] placeholder:text-faint",
              "focus:border-accent/50 focus:shadow-lift focus:outline-none",
            )}
          />
          {act ? (
            <button
              onClick={() => setAct(null)}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent hover:opacity-80"
            >
              {act} ×
            </button>
          ) : null}
        </div>

        <div className="mt-4">
          {searching ? (
            <div className="space-y-px overflow-hidden rounded-xl border border-border">
              <Skeleton className="h-16 rounded-none" />
              <Skeleton className="h-16 rounded-none" />
            </div>
          ) : results === null ? (
            <p className="px-1 py-6 text-center text-[12px] text-faint">
              Try “302”, “murder”, or “bail” — exact section numbers rank first.
            </p>
          ) : results.length === 0 ? (
            <p className="px-1 py-6 text-center text-[13px] text-muted">
              No sections match — that act may not be ingested yet (registry supports IPC, CrPC,
              Evidence Act, Constitution, BNS, BNSS, BSA).
            </p>
          ) : (
            <motion.ul
              variants={staggerParent}
              initial="hidden"
              animate="show"
              className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-card"
            >
              {results.map((s, i) => (
                <motion.li key={`${s.act_version}-${s.section_number}-${i}`} variants={riseIn} className="px-5 py-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-serif text-[17px]">s.{s.section_number}</span>
                    <span className="text-[13px] font-medium">{s.section_title ?? "—"}</span>
                    <Badge tone="neutral">{s.act_version}</Badge>
                    {s.exact ? <Badge tone="accent">exact match</Badge> : null}
                    {s.status !== "active" ? <Badge tone="warn">{s.status}</Badge> : null}
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[12.5px] leading-relaxed text-muted">{s.snippet}</p>
                  <div className="tnum mt-1.5 text-[11px] text-faint">
                    in force {s.effective_from ?? "?"} → {s.effective_to ?? "present"}
                    {s.chapter_path ? ` · ${s.chapter_path}` : ""}
                  </div>
                </motion.li>
              ))}
            </motion.ul>
          )}
        </div>
      </div>
    </div>
  );
}
