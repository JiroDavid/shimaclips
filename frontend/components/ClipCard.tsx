import type { Clip } from "@/lib/api";

function formatDuration(s: number): string {
  const total = Math.round(s);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export default function ClipCard({
  clip,
  rank,
  checked,
  onToggle,
}: {
  clip: Clip;
  rank: number;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={`block cursor-pointer overflow-hidden rounded-lg border bg-zinc-900 transition ${
        checked ? "border-purple-500" : "border-zinc-800 opacity-60"
      }`}
    >
      <div className="relative">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={clip.thumbnail_url} alt="" className="aspect-video w-full object-cover" />
        <span className="absolute left-2 top-2 rounded bg-black/70 px-2 py-0.5 text-xs font-semibold">#{rank}</span>
        <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-xs">
          {formatDuration(clip.duration)}
        </span>
        <input type="checkbox" checked={checked} onChange={onToggle} className="absolute right-2 top-2 h-5 w-5 accent-purple-500" />
      </div>
      <div className="space-y-1 p-3">
        <p className="line-clamp-2 text-sm font-medium">{clip.title}</p>
        <p className="text-xs text-zinc-400">
          {clip.view_count.toLocaleString()} views - clipped by {clip.creator_name}
        </p>
        <p className="text-xs text-zinc-500">{new Date(clip.created_at).toISOString().slice(0, 10)}</p>
        <a
          href={clip.url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-xs text-purple-400 hover:underline"
        >
          Open on Twitch
        </a>
      </div>
    </label>
  );
}
