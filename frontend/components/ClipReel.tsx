import ClipCard from "@/components/ClipCard";
import type { Clip } from "@/lib/api";
import type { Selection } from "@/lib/selection";

export default function ClipReel({
  title,
  clips,
  total,
  hasMore,
  capped = false,
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
  hasMore: boolean;
  capped?: boolean;
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
          {clips.length} of {total}
        </span>
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
      {capped && <p className="text-sm text-zinc-400">Showing the top 100</p>}
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
