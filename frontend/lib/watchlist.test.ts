import { describe, expect, it } from "vitest";
import type { WatchEntry } from "@/lib/api";
import { isWatched, lastRefreshedLabel, mergeEntry, progressFraction, stateLabel } from "@/lib/watchlist";

const e = (o: Partial<WatchEntry> = {}): WatchEntry => ({
  login: "arky",
  display_name: "Arky",
  paused: false,
  last_refreshed: null,
  state: "waiting",
  windows_done: 0,
  windows_total: 0,
  ...o,
});

describe("watchlist helpers", () => {
  it("labels states", () => {
    expect(stateLabel(e())).toBe("Waiting");
    expect(stateLabel(e({ state: "loading", windows_done: 3, windows_total: 10 }))).toBe("Loading 3/10");
    expect(stateLabel(e({ state: "loading" }))).toBe("Loading");
    expect(stateLabel(e({ state: "up_to_date" }))).toBe("Up to date");
    expect(stateLabel(e({ state: "paused" }))).toBe("Paused");
    expect(stateLabel(e({ state: "error" }))).toBe("Error");
  });

  it("computes a clamped progress fraction only while loading", () => {
    expect(progressFraction(e({ state: "loading", windows_done: 1, windows_total: 4 }))).toBe(0.25);
    expect(progressFraction(e({ state: "loading", windows_done: 9, windows_total: 4 }))).toBe(1);
    expect(progressFraction(e({ state: "loading", windows_total: 0 }))).toBe(0);
    expect(progressFraction(e({ state: "up_to_date", windows_done: 4, windows_total: 4 }))).toBe(0);
  });

  it("detects watched logins case-insensitively", () => {
    expect(isWatched([e()], "ARKY")).toBe(true);
    expect(isWatched([e()], "other")).toBe(false);
    expect(isWatched([e()], null)).toBe(false);
  });

  it("merges entries by login", () => {
    const a = e();
    const b = e({ login: "ludwig" });
    expect(mergeEntry([a], b)).toEqual([a, b]);
    const a2 = e({ state: "paused" });
    expect(mergeEntry([a, b], a2)).toEqual([a2, b]);
  });

  it("formats last refreshed", () => {
    const now = Date.parse("2026-11-08T12:00:00Z");
    expect(lastRefreshedLabel(null, now)).toBe("Never refreshed");
    expect(lastRefreshedLabel("2026-11-08T11:59:30Z", now)).toBe("Refreshed just now");
    expect(lastRefreshedLabel("2026-11-08T11:30:00Z", now)).toBe("Refreshed 30 min ago");
    expect(lastRefreshedLabel("2026-11-08T09:00:00Z", now)).toBe("Refreshed 3 h ago");
    expect(lastRefreshedLabel("2026-11-05T12:00:00Z", now)).toBe("Refreshed 3 d ago");
  });
});
