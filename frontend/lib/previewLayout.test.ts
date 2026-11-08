import { describe, expect, it } from "vitest";
import { embedUrl, placePopup } from "./previewLayout";

const popup = { w: 480, h: 270 };
const viewport = { w: 1280, h: 800 };

describe("embedUrl", () => {
  it("encodes values", () => {
    expect(embedUrl("a b&c", "x.y")).toBe(
      "https://clips.twitch.tv/embed?clip=a%20b%26c&parent=x.y&autoplay=true&muted=true",
    );
  });
});

describe("placePopup", () => {
  it("prefers the right of the card", () => {
    const pos = placePopup({ left: 100, top: 100, right: 400, bottom: 300 }, popup, viewport, 8);
    expect(pos).toEqual({ left: 408, top: 100 });
  });
  it("flips left near the right edge", () => {
    const pos = placePopup({ left: 900, top: 100, right: 1200, bottom: 300 }, popup, viewport, 8);
    expect(pos).toEqual({ left: 412, top: 100 });
  });
  it("goes below when neither side fits", () => {
    const pos = placePopup({ left: 100, top: 100, right: 1200, bottom: 300 }, popup, viewport, 8);
    expect(pos.top).toBe(308);
  });
  it("clamps inside the viewport", () => {
    const pos = placePopup({ left: 100, top: 700, right: 400, bottom: 790 }, popup, viewport, 8);
    expect(pos.top).toBe(800 - 270);
    const tiny = placePopup({ left: 0, top: 0, right: 300, bottom: 200 }, popup, { w: 300, h: 200 }, 8);
    expect(tiny).toEqual({ left: 0, top: 0 });
  });
});
