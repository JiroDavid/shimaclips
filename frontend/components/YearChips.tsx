"use client";

import type { YearInfo } from "@/lib/api";

const BADGE: Record<YearInfo["state"], { dot: string; label: string }> = {
  exact: { dot: "bg-green-500", label: "exact" },
  approximate: { dot: "bg-amber-500", label: "approximate" },
  empty: { dot: "bg-zinc-500", label: "not loaded" },
};

export default function YearChips({
  years,
  pending,
  error,
  onToggle,
}: {
  years: YearInfo[];
  pending: ReadonlySet<number>;
  error: string | null;
  onToggle: (year: number, enabled: boolean) => void;
}) {
  if (years.length === 0) return null;
  const ordered = [...years].sort((a, b) => a.year - b.year);
  return (
    <div className="space-y-2">
      <p className="text-xs text-zinc-500">Exact loading: switch a year on to load its exact counts</p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {ordered.map((y) => {
          const badge = BADGE[y.state];
          return (
            <div key={y.year} className="flex items-center gap-2 rounded border border-zinc-800 px-2 py-1 text-xs">
              <span className="font-semibold text-zinc-200">{y.year}</span>
              <span className="flex items-center gap-1 text-zinc-400">
                <span className={`inline-block h-2 w-2 rounded-full ${badge.dot}`} />
                {badge.label}
              </span>
              <span className="text-zinc-400">{y.clips.toLocaleString()}</span>
              <button
                type="button"
                role="switch"
                aria-checked={y.enabled}
                aria-label={`Exact ${y.year}`}
                disabled={pending.has(y.year)}
                onClick={() => onToggle(y.year, !y.enabled)}
                className="flex items-center gap-1 text-zinc-400 disabled:opacity-50"
              >
                <span
                  className={`relative inline-block h-4 w-7 rounded-full ${y.enabled ? "bg-green-600" : "bg-zinc-700"}`}
                >
                  <span
                    className={`absolute top-0.5 h-3 w-3 rounded-full bg-zinc-100 transition-all ${y.enabled ? "left-3.5" : "left-0.5"}`}
                  />
                </span>
                Exact
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
