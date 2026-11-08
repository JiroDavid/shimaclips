import type { Rect } from "./previewLayout";

export type PreviewState = { clipId: string; rect: Rect } | null;

export type PreviewController = {
  enter(clipId: string, rect: Rect): void;
  leave(): void;
  popupEnter(): void;
  popupLeave(): void;
  close(): void;
  subscribe(fn: (s: PreviewState) => void): () => void;
};

export function createPreviewController(opts: {
  delayMs?: number;
  graceMs?: number;
  timers?: { set: typeof setTimeout; clear: typeof clearTimeout };
}): PreviewController {
  const delayMs = opts.delayMs ?? 400;
  const graceMs = opts.graceMs ?? 150;
  const set = opts.timers?.set ?? ((...a: Parameters<typeof setTimeout>) => setTimeout(...a));
  const clear = opts.timers?.clear ?? ((id: Parameters<typeof clearTimeout>[0]) => clearTimeout(id));
  const listeners = new Set<(s: PreviewState) => void>();
  let current: PreviewState = null;
  let openTimer: ReturnType<typeof setTimeout> | null = null;
  let closeTimer: ReturnType<typeof setTimeout> | null = null;
  let overPopup = false;

  function cancelOpen() {
    if (openTimer !== null) clear(openTimer);
    openTimer = null;
  }
  function cancelClose() {
    if (closeTimer !== null) clear(closeTimer);
    closeTimer = null;
  }
  function publish(next: PreviewState) {
    current = next;
    for (const fn of Array.from(listeners)) fn(next);
  }
  function scheduleClose() {
    cancelClose();
    if (!current) return;
    closeTimer = set(() => {
      closeTimer = null;
      overPopup = false;
      publish(null);
    }, graceMs);
  }

  return {
    enter(clipId, rect) {
      cancelOpen();
      cancelClose();
      if (current?.clipId === clipId) return;
      openTimer = set(() => {
        openTimer = null;
        cancelClose();
        publish({ clipId, rect });
      }, delayMs);
    },
    leave() {
      if (overPopup) return;
      cancelOpen();
      scheduleClose();
    },
    popupEnter() {
      overPopup = true;
      cancelClose();
    },
    popupLeave() {
      overPopup = false;
      scheduleClose();
    },
    close() {
      overPopup = false;
      cancelOpen();
      cancelClose();
      if (current) publish(null);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
  };
}
