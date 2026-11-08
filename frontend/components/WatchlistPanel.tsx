"use client";

import { useState } from "react";
import type { WatchEntry } from "@/lib/api";
import { lastRefreshedLabel, progressFraction, stateLabel } from "@/lib/watchlist";

export default function WatchlistPanel({
  entries,
  error,
  now,
  pending,
  onOpen,
  onRemove,
  onSetPaused,
}: {
  entries: WatchEntry[];
  error: string | null;
  now: number;
  pending: ReadonlySet<string>;
  onOpen: (login: string) => void;
  onRemove: (login: string) => void;
  onSetPaused: (login: string, paused: boolean) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <section className="rounded border border-zinc-800">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold hover:bg-zinc-900"
      >
        <span>Watchlist ({entries.length})</span>
        <span className="text-zinc-400">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-zinc-800 p-3">
          {error && <p className="text-sm text-red-400">{error}</p>}
          {entries.length === 0 && !error && (
            <p className="text-sm text-zinc-400">No streamers are being kept up to date.</p>
          )}
          {entries.map((e) => {
            const busy = pending.has(e.login.toLowerCase());
            const frac = progressFraction(e);
            return (
              <div key={e.login} className="space-y-1 rounded bg-zinc-900 p-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    onClick={() => onOpen(e.login)}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {e.display_name}
                  </button>
                  <div className="flex gap-2">
                    <button
                      onClick={() => onSetPaused(e.login, !e.paused)}
                      disabled={busy}
                      className="rounded border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800 disabled:opacity-50"
                    >
                      {e.paused ? "Resume" : "Pause"}
                    </button>
                    <button
                      onClick={() => onRemove(e.login)}
                      disabled={busy}
                      className="rounded border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800 disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </div>
                </div>
                <p className="text-xs text-zinc-400">
                  {stateLabel(e)} - {lastRefreshedLabel(e.last_refreshed, now)}
                </p>
                {e.state === "loading" && (
                  <div className="h-1 overflow-hidden rounded bg-zinc-800">
                    <div
                      className="h-full bg-purple-500 transition-all"
                      style={{ width: `${Math.round(frac * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
