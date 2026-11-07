import ClipCard from "@/components/ClipCard";
import type { Clip } from "@/lib/api";
import type { Selection } from "@/lib/selection";

export default function ClipReel({
  title,
  clips,
  total,
  exact,
  sort,
  onSortChange,
  yearFilter,
  hasMore,
  onShowMore,
  loading,
  loadingNote = false,
  selection,
  onToggle,
  error,
  action,
}: {
  title: string;
  clips: Clip[];
  total: number;
  exact: boolean;
  sort: "views" | "newest";
  onSortChange: (sort: "views" | "newest") => void;
  yearFilter?: { value: number | null; years: number[]; onChange: (year: number | null) => void };
  hasMore: boolean;
  onShowMore: () => void;
  loading: boolean;
  loadingNote?: boolean;
  selection: Selection;
  onToggle: (clip: Clip) => void;
  error?: string | null;
  action?: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold">{title}</h2>
        <span className="text-sm text-zinc-400">
          {exact ? `${clips.length} of ${total}` : `${clips.length} loaded so far`}
        </span>
        <select
          aria-label="Sort"
          value={sort}
          onChange={(e) => onSortChange(e.target.value as "views" | "newest")}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs"
        >
          <option value="views">Most viewed</option>
          <option value="newest" disabled={!exact} title="Needs a fully loaded period">
            Newest
          </option>
        </select>
        {yearFilter && (
          <select
            aria-label="Year"
            value={yearFilter.value ?? ""}
            onChange={(e) => yearFilter.onChange(e.target.value === "" ? null : Number(e.target.value))}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs"
          >
            <option value="">All time</option>
            {[...yearFilter.years]
              .sort((a, b) => b - a)
              .map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
          </select>
        )}
        {loadingNote && <span className="text-xs text-zinc-500">still loading, may reorder</span>}
        {action}
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
      {total === 0 && !loading && clips.length === 0 && !error && <p className="text-sm text-zinc-400">No clips here yet</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((clip, i) => (
          <ClipCard key={clip.id} clip={clip} rank={i + 1} checked={selection.has(clip.id)} onToggle={() => onToggle(clip)} />
        ))}
      </div>
      {hasMore && (
        <button
          onClick={onShowMore}
          disabled={loading}
          className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
        >
          Show more
        </button>
      )}
    </section>
  );
}
