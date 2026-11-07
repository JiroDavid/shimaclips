"use client";

import { useEffect, useState } from "react";
import type { LoadState } from "@/lib/api";
import { bannerMessage } from "@/lib/loadingMessages";

const MESSAGE_PERIOD_MS = 4000;

export default function LoadingBanner({
  state,
  startedAt,
  error,
  onRetry,
}: {
  state: LoadState | null;
  startedAt: number | null;
  error: string | null;
  onRetry: () => void;
}) {
  const [mountedAt] = useState(() => Date.now());
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const origin = startedAt ?? mountedAt;
    const id = setInterval(() => setElapsedMs(Math.max(0, Date.now() - origin)), 1000);
    return () => clearInterval(id);
  }, [startedAt, mountedAt]);

  const messageTick = Math.floor(elapsedMs / MESSAGE_PERIOD_MS);
  const { text, slow } = bannerMessage(elapsedMs, messageTick);
  const pct = state && state.windows_total > 0 ? Math.min(100, (state.windows_done / state.windows_total) * 100) : 0;

  return (
    <div className="space-y-3">
      {!error && (
        <div className={`space-y-2 rounded-lg border bg-zinc-900 p-4 ${slow ? "border-amber-600" : "border-zinc-800"}`}>
          <p className={`text-sm ${slow ? "text-amber-300" : "text-zinc-300"}`}>{text}</p>
          <div className="h-2 overflow-hidden rounded bg-zinc-800">
            <div className="h-full bg-purple-600 transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-zinc-400">{(state?.clips ?? 0).toLocaleString()} clips loaded</p>
          {state && (state.status === "queued" || state.status === "running") && (
            <p className="text-xs text-zinc-400">
              Clips and the approximate calendar are usable now - exact counts keep loading
            </p>
          )}
        </div>
      )}
      {state && state.capped > 0 && (
        <p className="text-xs text-zinc-400">{state.capped.toLocaleString()} busy hours could not be fully loaded</p>
      )}
      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-red-900 bg-red-950 p-3 text-sm text-red-300">
          <span>{error}</span>
          <button onClick={onRetry} className="rounded border border-red-800 px-3 py-1 hover:bg-red-900">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
