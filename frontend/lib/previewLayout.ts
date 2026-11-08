export type Rect = { left: number; top: number; right: number; bottom: number };

export function embedUrl(clipId: string, hostname: string): string {
  return `https://clips.twitch.tv/embed?clip=${encodeURIComponent(clipId)}&parent=${encodeURIComponent(hostname)}&autoplay=true&muted=true`;
}

function clamp(v: number, size: number, limit: number): number {
  return Math.max(0, Math.min(v, limit - size));
}

export function placePopup(
  anchor: Rect,
  popup: { w: number; h: number },
  viewport: { w: number; h: number },
  gap = 8,
): { left: number; top: number } {
  let left: number;
  let top: number;
  if (anchor.right + gap + popup.w <= viewport.w) {
    left = anchor.right + gap;
    top = anchor.top;
  } else if (anchor.left - gap - popup.w >= 0) {
    left = anchor.left - gap - popup.w;
    top = anchor.top;
  } else {
    left = anchor.left;
    top = anchor.bottom + gap;
  }
  return { left: clamp(left, popup.w, viewport.w), top: clamp(top, popup.h, viewport.h) };
}
