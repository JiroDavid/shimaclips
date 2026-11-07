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
