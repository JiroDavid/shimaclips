import { describe, expect, it } from "vitest";
import { shouldFallBackToViews } from "./sort";

describe("shouldFallBackToViews", () => {
  it("falls back when newest is settled on a non-exact range", () => {
    expect(shouldFallBackToViews("newest", false, false)).toBe(true);
  });
  it("keeps newest while loading or when exact", () => {
    expect(shouldFallBackToViews("newest", true, false)).toBe(false);
    expect(shouldFallBackToViews("newest", false, true)).toBe(false);
  });
  it("never changes views", () => {
    expect(shouldFallBackToViews("views", false, false)).toBe(false);
  });
});
