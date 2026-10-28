import { useEffect, useState } from "react";

// Hash routing (#/documents/abc) — works when the UI is served as static files
// by nginx or by FastAPI, with no server-side route config.
export type Route =
  | { page: "documents" }
  | { page: "upload" }
  | { page: "document"; id: string }
  | { page: "evaluation" }
  | { page: "settings" };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "documents" && parts[1]) return { page: "document", id: parts[1] };
  if (parts[0] === "upload") return { page: "upload" };
  if (parts[0] === "evaluation") return { page: "evaluation" };
  if (parts[0] === "settings") return { page: "settings" };
  return { page: "documents" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = path;
}
