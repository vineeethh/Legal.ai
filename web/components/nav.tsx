"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { API_URL } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/components/ui";

const LINKS = [
  { href: "/", label: "Docket" },
  { href: "/kb", label: "Statutes" },
  { href: "/settings", label: "Settings" },
];

/** System health, checked quietly. A product that knows its own state reads
 *  as engineered; a red banner reads as broken. */
function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () =>
      fetch(`${API_URL}/api/health`, { signal: AbortSignal.timeout(4000) })
        .then((r) => alive && setOk(r.ok))
        .catch(() => alive && setOk(false));
    check();
    const t = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return (
    <span
      title={ok === null ? "Checking…" : ok ? "API connected" : "API unreachable — docker compose up api"}
      className="mr-1 flex items-center gap-1.5 text-[11px] text-faint"
    >
      <span
        className={cn(
          "inline-block h-[5px] w-[5px] rounded-full",
          ok === null ? "bg-faint" : ok ? "bg-success" : "bg-danger",
        )}
      />
      <span className="hidden lg:inline">{ok === false ? "offline" : ok ? "live" : ""}</span>
    </span>
  );
}

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-0.5">
      <HealthDot />
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" || pathname.startsWith("/documents") : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "t-state relative rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
              active ? "text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {link.label}
            <span
              className={cn(
                "t-move absolute inset-x-2.5 -bottom-[13px] h-px bg-foreground transition-opacity",
                active ? "opacity-100" : "opacity-0",
              )}
            />
          </Link>
        );
      })}
      <div className="ml-2 border-l border-border pl-2">
        <ThemeToggle />
      </div>
    </nav>
  );
}
