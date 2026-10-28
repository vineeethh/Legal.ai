import { useEffect, useState } from "react";

import { api } from "./api";
import { DocumentPage } from "./pages/DocumentPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";
import { useRoute } from "./router";
import type { Health } from "./types";

const NAV = [
  { href: "#/documents", label: "Judgments", pages: ["documents", "document"] },
  { href: "#/upload", label: "New analysis", pages: ["upload"] },
  { href: "#/evaluation", label: "Evaluation", pages: ["evaluation"] },
  { href: "#/settings", label: "Settings", pages: ["settings"] },
];

export function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, [route.page]);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/documents">
            ⚖️ Legal.ai
          </a>
          <nav className="nav">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className={n.pages.includes(route.page) ? "active" : ""}>
                {n.label}
              </a>
            ))}
          </nav>
          {offline ? (
            <span className="badge bad">API offline</span>
          ) : health?.mode === "demo" ? (
            <span className="badge warn" title="Results are synthetic; the real pipeline is not running.">
              Demo mode
            </span>
          ) : health ? (
            <span className="badge ok">Live</span>
          ) : null}
        </div>
      </header>
      <main>
        {route.page === "documents" && <DocumentsPage />}
        {route.page === "upload" && <UploadPage health={health} />}
        {route.page === "document" && <DocumentPage key={route.id} id={route.id} />}
        {route.page === "evaluation" && <EvaluationPage />}
        {route.page === "settings" && <SettingsPage health={health} />}
      </main>
    </>
  );
}
