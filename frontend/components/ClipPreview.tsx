"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { PreviewController, PreviewState } from "@/lib/previewController";
import { embedUrl, placePopup } from "@/lib/previewLayout";

const POPUP = { w: 480, h: 270 };
const FOOTER = 28;

export const PreviewContext = createContext<PreviewController | null>(null);

export function usePreviewController(): PreviewController | null {
  return useContext(PreviewContext);
}

export default function ClipPreview({ controller }: { controller: PreviewController }) {
  const [active, setActive] = useState<PreviewState>(null);

  useEffect(() => controller.subscribe(setActive), [controller]);

  const open = active !== null;
  useEffect(() => {
    if (!open) return;
    const close = () => controller.close();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") controller.close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open, controller]);

  if (!active) return null;
  const pos = placePopup(active.rect, { w: POPUP.w, h: POPUP.h + FOOTER }, { w: window.innerWidth, h: window.innerHeight });
  return createPortal(
    <div
      key={active.clipId}
      onPointerEnter={() => controller.popupEnter()}
      onPointerLeave={() => controller.popupLeave()}
      style={{ position: "fixed", left: pos.left, top: pos.top, width: POPUP.w, zIndex: 50 }}
      className="overflow-hidden rounded-lg border border-zinc-700 bg-black shadow-2xl"
    >
      <iframe
        src={embedUrl(active.clipId, window.location.hostname)}
        title="Clip preview"
        allow="autoplay; fullscreen"
        allowFullScreen
        style={{ width: POPUP.w, height: POPUP.h }}
        className="block border-0"
      />
      <a
        href={`https://clips.twitch.tv/${encodeURIComponent(active.clipId)}`}
        target="_blank"
        rel="noreferrer"
        style={{ height: FOOTER }}
        className="flex items-center px-3 text-xs text-purple-400 hover:underline"
      >
        Open on Twitch
      </a>
    </div>,
    document.body,
  );
}
