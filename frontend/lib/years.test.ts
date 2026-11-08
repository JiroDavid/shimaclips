import { describe, expect, it } from "vitest";
import type { YearInfo } from "@/lib/api";
import { hasOlderApproximate } from "./years";

const y = (state: YearInfo["state"], enabled: boolean) => ({ year: 2020, state, enabled }) as YearInfo;

describe("hasOlderApproximate", () => {
  it("is true for an approximate year that is switched off", () => {
    expect(hasOlderApproximate([y("exact", true), y("approximate", false)])).toBe(true);
  });
  it("ignores approximate years that are switched on", () => {
    expect(hasOlderApproximate([y("approximate", true)])).toBe(false);
  });
});
