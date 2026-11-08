"use client";

import { useEffect, useRef } from "react";
import { usePreviewController } from "@/components/ClipPreview";
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
  const controller = usePreviewController();
  const entered = useRef(false);

  useEffect(
    () => () => {
      if (entered.current) controller?.leave();
    },
    [controller],
  );

  function enter(el: HTMLElement) {
    if (!controller) return;
    entered.current = true;
    const r = el.getBoundingClientRect();
    controller.enter(clip.id, { left: r.left, top: r.top, right: r.right, bottom: r.bottom });
  }

  function leave() {
    if (!entered.current) return;
    entered.current = false;
    controller?.leave();
  }

  return (
    <label
      onPointerEnter={(e) => {
        if (e.pointerType !== "touch") enter(e.currentTarget);
      }}
      onPointerLeave={(e) => {
        if (e.pointerType !== "touch") leave();
      }}
      onFocus={(e) => enter(e.currentTarget)}
      onBlur={leave}
      className={`block cursor-pointer overflow-hidden rounded-lg border bg-zinc-900 transition ${
        checked ? "border-purple-500" : "border-zinc-800"
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
