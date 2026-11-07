import { describe, expect, it } from "vitest";
import { moveIndex } from "./searchNav";

describe("moveIndex", () => {
  it("wraps down from last to first", () => expect(moveIndex(2, 1, 3)).toBe(0));
  it("wraps up from first to last", () => expect(moveIndex(0, -1, 3)).toBe(2));
  it("moves within range", () => {
    expect(moveIndex(0, 1, 3)).toBe(1);
    expect(moveIndex(2, -1, 3)).toBe(1);
  });
  it("from none goes to first on down and last on up", () => {
    expect(moveIndex(-1, 1, 3)).toBe(0);
    expect(moveIndex(-1, -1, 3)).toBe(2);
  });
  it("returns -1 for an empty list", () => {
    expect(moveIndex(-1, 1, 0)).toBe(-1);
    expect(moveIndex(0, -1, 0)).toBe(-1);
  });
  it("handles a single row", () => {
    expect(moveIndex(0, 1, 1)).toBe(0);
    expect(moveIndex(0, -1, 1)).toBe(0);
    expect(moveIndex(-1, 1, 1)).toBe(0);
    expect(moveIndex(-1, -1, 1)).toBe(0);
  });
});
