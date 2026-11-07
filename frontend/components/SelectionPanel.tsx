import { formatClipDate, pluralClips, type Selection } from "@/lib/selection";

export default function SelectionPanel({
  selection,
  onRemove,
  onClear,
  onDownload,
  downloading,
}: {
  selection: Selection;
  onRemove: (id: string) => void;
  onClear: () => void;
  onDownload: () => void;
  downloading: boolean;
}) {
  if (selection.size === 0) return null;
  const clips = Array.from(selection.values());
  return (
    <div className="space-y-3 rounded-lg border border-zinc-700 bg-zinc-900 p-4 shadow-lg shadow-black/50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-semibold">{pluralClips(clips.length)}</p>
        <div className="flex gap-3">
          <button onClick={onClear} className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800">
            Clear all
          </button>
          <button
            onClick={onDownload}
            disabled={downloading}
            className="rounded bg-purple-600 px-4 py-2 text-sm font-medium hover:bg-purple-500 disabled:opacity-50"
          >
            {downloading ? "Downloading..." : `Download ${clips.length}`}
          </button>
        </div>
      </div>
      <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
        {clips.map((c) => (
          <li key={c.id} className="flex items-center gap-3">
            <span className="min-w-0 flex-1 truncate text-zinc-200">{c.title}</span>
            <span className="shrink-0 text-zinc-400">{c.view_count.toLocaleString()} views</span>
            <span className="shrink-0 text-zinc-500">{formatClipDate(c.created_at)}</span>
            <button
              onClick={() => onRemove(c.id)}
              aria-label={`Remove ${c.title} from selection`}
              className="shrink-0 rounded px-2 py-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
