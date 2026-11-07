import { describe, expect, it } from "vitest";
import type { Clip } from "./api";
import { emptySelection, pluralClips, removeClip, toggleClip } from "./selection";

const clip = (id: string, created_at: string): Clip => ({
  id,
  url: `https://clips.twitch.tv/${id}`,
  title: id,
  thumbnail_url: "",
  view_count: 1,
  duration: 10,
  creator_name: "x",
  created_at,
});

describe("selection", () => {
  it("toggle adds then removes without mutating input", () => {
    const empty = emptySelection();
    const a = clip("a", "2026-01-01T00:00:00Z");
    const one = toggleClip(empty, a);
    expect(empty.size).toBe(0);
    expect(one.has("a")).toBe(true);
    const none = toggleClip(one, a);
    expect(one.size).toBe(1);
    expect(none.size).toBe(0);
  });

  it("spans clips from different periods", () => {
    let sel = emptySelection();
    sel = toggleClip(sel, clip("a", "2026-01-01T00:00:00Z"));
    sel = toggleClip(sel, clip("b", "2026-09-01T00:00:00Z"));
    expect([...sel.keys()]).toEqual(["a", "b"]);
  });

  it("removeClip returns a new map", () => {
    const sel = toggleClip(emptySelection(), clip("a", "2026-01-01T00:00:00Z"));
    const next = removeClip(sel, "a");
    expect(next.size).toBe(0);
    expect(sel.size).toBe(1);
  });
});

describe("pluralClips", () => {
  it("uses singular for one and plural otherwise", () => {
    expect(pluralClips(1)).toBe("1 clip selected");
    expect(pluralClips(3)).toBe("3 clips selected");
  });
});
