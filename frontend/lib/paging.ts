import type { Clip } from "./api";

export const MAX_PAGE = 100;

export function nextPage(
  fetched: number,
  limit: number,
  hasMore: boolean | null,
): { offset: number; limit: number } | null {
  if (hasMore === false || fetched >= limit) return null;
  return { offset: fetched, limit: Math.min(MAX_PAGE, limit - fetched) };
}

export function appendUnique(clips: Clip[], more: Clip[]): Clip[] {
  const seen = new Set(clips.map((c) => c.id));
  return [...clips, ...more.filter((c) => !seen.has(c.id) && seen.add(c.id))];
}
