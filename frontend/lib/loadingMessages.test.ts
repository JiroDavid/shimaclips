import { describe, expect, it } from "vitest";
import { bannerMessage } from "./loadingMessages";

describe("bannerMessage", () => {
  it("slow flips after 20000", () => {
    expect(bannerMessage(20000, 0).slow).toBe(false);
    expect(bannerMessage(20001, 0).slow).toBe(true);
    expect(bannerMessage(0, 0).slow).toBe(false);
  });

  it("message changes with tick", () => {
    expect(bannerMessage(1000, 0).text).not.toBe(bannerMessage(1000, 1).text);
    expect(bannerMessage(30000, 0).text).not.toBe(bannerMessage(30000, 1).text);
  });

  it("slow pool mentions popular streamer", () => {
    const texts = [0, 1, 2, 3].map((t) => bannerMessage(30000, t).text);
    expect(texts).toContain("this streamer seems to be quite popular, loading clips will take a minute");
  });

  it("very slow message after 90000", () => {
    const m = bannerMessage(90001, 0);
    expect(m.slow).toBe(true);
    expect(m.text).toContain("still going, this one is big");
    expect(bannerMessage(90000, 0).text).not.toContain("still going, this one is big");
  });

  it("tick wraps around", () => {
    expect(bannerMessage(1000, 100).text).toBeTruthy();
  });
});
