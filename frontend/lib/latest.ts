export type LatestResult<T> = { ok: true; value: T } | { ok: false };

export function createLatest() {
  let current: AbortController | null = null;
  return {
    async run<T>(fn: (signal: AbortSignal) => Promise<T>): Promise<LatestResult<T>> {
      current?.abort();
      const ctrl = new AbortController();
      current = ctrl;
      try {
        const value = await fn(ctrl.signal);
        if (current !== ctrl) return { ok: false };
        return { ok: true, value };
      } catch (e) {
        if (current !== ctrl || (e instanceof Error && e.name === "AbortError")) return { ok: false };
        throw e;
      }
    },
  };
}
