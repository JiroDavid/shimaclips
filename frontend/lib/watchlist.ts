import type { WatchEntry } from "@/lib/api";

export function stateLabel(e: WatchEntry): string {
  switch (e.state) {
    case "waiting":
      return "Waiting";
    case "loading":
      return e.windows_total > 0 ? `Loading ${e.windows_done}/${e.windows_total}` : "Loading";
    case "up_to_date":
      return "Up to date";
    case "paused":
      return "Paused";
    case "error":
      return "Error";
  }
}

export function progressFraction(e: WatchEntry): number {
  if (e.state !== "loading" || e.windows_total <= 0) return 0;
  return Math.min(1, Math.max(0, e.windows_done / e.windows_total));
}

export function isWatched(entries: WatchEntry[], login: string | null): boolean {
  if (!login) return false;
  const l = login.toLowerCase();
  return entries.some((e) => e.login.toLowerCase() === l);
}

export function combineErrors(action: string | null, poll: string | null): string | null {
  return action ?? poll;
}

export function lastRefreshedLabel(iso: string | null, now: number): string {
  if (!iso) return "Never refreshed";
  const ms = now - Date.parse(iso);
  if (!Number.isFinite(ms)) return "Never refreshed";
  const min = Math.floor(ms / 60000);
  if (min < 1) return "Refreshed just now";
  if (min < 60) return `Refreshed ${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `Refreshed ${h} h ago`;
  return `Refreshed ${Math.floor(h / 24)} d ago`;
}
