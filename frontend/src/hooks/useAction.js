import { useState } from "react";

/** Wrap a mutation: {run, busy, error, clear}. `run` resolves to the result or undefined on error. */
export function useAction(fn) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(...args) {
    setBusy(true);
    setError(null);
    try {
      return await fn(...args);
    } catch (err) {
      setError(err);
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  return { run, busy, error, clear: () => setError(null) };
}
