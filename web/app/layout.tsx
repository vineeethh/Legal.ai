import type { Metadata } from "next";
import { Fraunces, Geist } from "next/font/google";
import Link from "next/link";
import { Nav } from "@/components/nav";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  axes: ["opsz", "SOFT"],
});

export const metadata: Metadata = {
  title: "Legal.ai — Judgment Extraction",
  description:
    "Provenance-backed structured extraction from Indian court judgments. Every value traceable to a verbatim span.",
};

// Applies the saved (or system) theme before first paint — no flash.
const themeScript = `
try {
  const t = localStorage.getItem("theme");
  const dark = t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
} catch {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      {/* suppressHydrationWarning: browser extensions (e.g. Grammarly) stamp
          attributes onto <body> before React hydrates — harmless, silenced. */}
      <body suppressHydrationWarning className={`${geist.variable} ${fraunces.variable} flex min-h-dvh flex-col`}>
        <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-md">
          <div className="mx-auto flex h-[54px] w-full max-w-6xl items-center justify-between px-5 sm:px-8">
            <Link href="/" className="flex items-baseline gap-2.5">
              <span className="font-serif text-[21px] font-medium leading-none tracking-tight">
                Legal<span className="text-accent">.ai</span>
              </span>
              <span className="mt-px hidden text-[10.5px] uppercase tracking-[0.14em] text-faint md:block">
                judgment extraction
              </span>
            </Link>
            <Nav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-12">{children}</main>
        <footer className="border-t border-border">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-1.5 px-5 py-5 text-[11px] leading-relaxed text-faint sm:flex-row sm:items-center sm:justify-between sm:px-8">
            <span>Every value traceable to a verbatim span — trust it, or knowingly distrust it.</span>
            <span className="tnum shrink-0">local · bring your own key</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
