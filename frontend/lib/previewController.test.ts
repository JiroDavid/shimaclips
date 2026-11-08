import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPreviewController } from "./previewController";

const rect = { left: 0, top: 0, right: 10, bottom: 10 };

function setup() {
  const c = createPreviewController({});
  const seen: (string | null)[] = [];
  c.subscribe((s) => seen.push(s ? s.clipId : null));
  return { c, seen };
}

describe("previewController", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("opens after the delay", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(399);
    expect(seen).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(seen).toEqual(["a"]);
  });

  it("sweep across cards opens only the last", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(200);
    c.leave();
    c.enter("b", rect);
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual(["b"]);
  });

  it("leave closes after the grace", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    c.leave();
    vi.advanceTimersByTime(149);
    expect(seen).toEqual(["a"]);
    vi.advanceTimersByTime(1);
    expect(seen).toEqual(["a", null]);
  });

  it("leave before the delay cancels the open", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    c.leave();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual([]);
  });

  it("popup enter cancels close and popup leave closes", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    c.leave();
    c.popupEnter();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual(["a"]);
    c.popupLeave();
    vi.advanceTimersByTime(150);
    expect(seen).toEqual(["a", null]);
  });

  it("only one preview at a time", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    c.leave();
    c.enter("b", rect);
    expect(seen).toEqual(["a"]);
    vi.advanceTimersByTime(400);
    expect(seen).toEqual(["a", "b"]);
  });

  it("re-entering the open card keeps it open", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    c.leave();
    c.enter("a", rect);
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual(["a"]);
  });

  it("close is immediate and idempotent", () => {
    const { c, seen } = setup();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    c.close();
    c.close();
    expect(seen).toEqual(["a", null]);
    c.enter("b", rect);
    c.close();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual(["a", null]);
  });

  it("unsubscribe stops notifications", () => {
    const c = createPreviewController({});
    const fn = vi.fn();
    const off = c.subscribe(fn);
    off();
    c.enter("a", rect);
    vi.advanceTimersByTime(400);
    expect(fn).not.toHaveBeenCalled();
  });
});
