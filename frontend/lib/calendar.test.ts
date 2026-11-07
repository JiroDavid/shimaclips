import { describe, expect, it } from "vitest";
import { heatLevel, monthDays, rangeOfKey, shiftMonth, shiftWeek, weekDays } from "./calendar";

describe("calendar", () => {
  it("weekDays starts monday", () => {
    expect(weekDays("2026-11-08")).toEqual([
      "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08",
    ]);
  });

  it("weekDays from a monday stays put", () => {
    expect(weekDays("2026-11-02")[0]).toBe("2026-11-02");
  });

  it("weekDays for a sunday anchor crosses a year boundary", () => {
    expect(weekDays("2027-01-01")[0]).toBe("2026-12-28");
    expect(weekDays("2027-01-01")[6]).toBe("2027-01-03");
    expect(weekDays("2026-01-04")[0]).toBe("2025-12-29");
    expect(weekDays("2026-01-04")[6]).toBe("2026-01-04");
  });

  it("shiftWeek forward across a month end", () => {
    expect(shiftWeek("2026-10-28", 1)).toBe("2026-11-04");
  });

  it("shiftWeek crosses month and year", () => {
    expect(shiftWeek("2026-11-08", 1)).toBe("2026-11-15");
    expect(shiftWeek("2026-01-03", -1)).toBe("2025-12-27");
  });

  it("shiftMonth crosses year boundaries", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-03", 14)).toBe("2027-05");
  });

  it("monthDays lists every day", () => {
    const days = monthDays(2026, 11);
    expect(days).toHaveLength(30);
    expect(days[0]).toBe("2026-11-01");
    expect(days[29]).toBe("2026-11-30");
    expect(monthDays(2028, 2)).toHaveLength(29);
  });

  it("heatLevel scales relative to max", () => {
    expect(heatLevel(0, 10)).toBe(0);
    expect(heatLevel(1, 10)).toBe(1);
    expect(heatLevel(10, 10)).toBe(5);
    expect(heatLevel(5, 0)).toBe(0);
    expect(heatLevel(5, 10)).toBe(3);
  });

  it("rangeOfKey handles year, month and day", () => {
    expect(rangeOfKey("2026-02")).toEqual({ start: "2026-02-01", end: "2026-02-28" });
    expect(rangeOfKey("2028-02")).toEqual({ start: "2028-02-01", end: "2028-02-29" });
    expect(rangeOfKey("2026")).toEqual({ start: "2026-01-01", end: "2026-12-31" });
    expect(rangeOfKey("2026-11-05")).toEqual({ start: "2026-11-05", end: "2026-11-05" });
  });
});
