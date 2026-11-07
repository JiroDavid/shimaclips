import type { Clip } from "./api";

export type Selection = ReadonlyMap<string, Clip>;

export function emptySelection(): Selection {
  return new Map();
}

export function toggleClip(sel: Selection, clip: Clip): Selection {
  const next = new Map(sel);
  if (next.has(clip.id)) next.delete(clip.id);
  else next.set(clip.id, clip);
  return next;
}

export function removeClip(sel: Selection, id: string): Selection {
  const next = new Map(sel);
  next.delete(id);
  return next;
}

export function pluralClips(n: number): string {
  return n === 1 ? "1 clip selected" : `${n} clips selected`;
}

export function formatClipDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "unknown date" : d.toISOString().slice(0, 10);
}

export function isNewStreamer(owner: string | null, login: string | null): boolean {
  return login !== null && login !== owner;
}
