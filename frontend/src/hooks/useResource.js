import { useCallback, useEffect, useRef, useState } from "react";

import { request } from "../lib/api";

/**
 * Fetch `path` (null = skip). Returns {data, error, loading, refetch}.
 * `pollMs` re-fetches on an interval while the tab is visible (chat 5s, dashboards 60s).
 */
export function useResource(path, { pollMs } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const controller = useRef(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!path) return;
      controller.current?.abort();
      const ctrl = new AbortController();
      controller.current = ctrl;
      if (!quiet) setState((s) => ({ ...s, loading: true }));
      try {
        const data = await request(path, { signal: ctrl.signal });
        setState({ data, error: null, loading: false });
      } catch (error) {
        if (error.name !== "AbortError") setState((s) => ({ data: quiet ? s.data : null, error, loading: false }));
      }
    },
    [path],
  );

  useEffect(() => {
    load();
    if (!pollMs) return () => controller.current?.abort();
    const id = setInterval(() => document.visibilityState === "visible" && load(true), pollMs);
    return () => {
      clearInterval(id);
      controller.current?.abort();
    };
  }, [load, pollMs]);

  return { ...state, refetch: () => load(true) };
}
