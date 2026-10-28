import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads `fetcher()` and re-runs it every `intervalMs` while `shouldPoll(data)`
 * is true. Returns the latest data, the last error and a manual `reload`.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  { intervalMs, shouldPoll, deps = [] }: { intervalMs: number; shouldPoll: (data: T | null) => boolean; deps?: unknown[] },
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  const shouldPollRef = useRef(shouldPoll);
  fetcherRef.current = fetcher;
  shouldPollRef.current = shouldPoll;

  const reload = useCallback(async () => {
    try {
      const next = await fetcherRef.current();
      setData(next);
      setError(null);
      return next;
    } catch (e) {
      setError(e as Error);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    setLoading(true);
    setData(null);

    const tick = async () => {
      const next = await reload();
      if (!cancelled && shouldPollRef.current(next)) {
        timer = window.setTimeout(tick, intervalMs);
      }
    };
    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [intervalMs, reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, error, loading, reload };
}
