import { describe, expect, it } from "vitest";
import type { Clip } from "./api";
import { appendUnique, nextPage } from "./paging";

const clip = (id: string): Clip => ({
  id,
  url: `https://clips.twitch.tv/${id}`,
  title: id,
  thumbnail_url: "",
  view_count: 1,
  duration: 10,
  creator_name: "x",
  created_at: "2026-01-01T00:00:00Z",
});

describe("nextPage", () => {
  it("asks for the whole limit in one page when it fits", () => {
    expect(nextPage(0, 10, null)).toEqual({ offset: 0, limit: 10 });
  });

  it("splits a large limit into pages of at most 100", () => {
    expect(nextPage(0, 250, null)).toEqual({ offset: 0, limit: 100 });
    expect(nextPage(100, 250, true)).toEqual({ offset: 100, limit: 100 });
    expect(nextPage(200, 250, true)).toEqual({ offset: 200, limit: 50 });
    expect(nextPage(250, 250, true)).toBeNull();
  });

  it("stops when the server says there is no more", () => {
    expect(nextPage(100, 250, false)).toBeNull();
    expect(nextPage(0, 10, false)).toBeNull();
  });

  it("keeps going while the server has more, even if the total grew", () => {
    expect(nextPage(100, 250, true)).toEqual({ offset: 100, limit: 100 });
  });
});

describe("appendUnique", () => {
  it("drops clips already present", () => {
    const out = appendUnique([clip("a"), clip("b")], [clip("b"), clip("c")]);
    expect(out.map((c) => c.id)).toEqual(["a", "b", "c"]);
  });
});
