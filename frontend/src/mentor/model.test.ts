import { describe, expect, it } from "vitest";
import { ALL_DAYS, WEEKDAYS, applyPreset, copyDay, dayProblem, emptyWeek, fromMinor, hasRanges, PRESETS, summarise, toMinor, weekFrom, windowsFrom } from "./model";

const monFri = () => weekFrom([0, 1, 2, 3, 4].flatMap((weekday) => [{ weekday, start: "10:00", end: "12:00" }, { weekday, start: "15:00", end: "17:00" }]));

describe("the weekly schedule", () => {
  it("round trips through the API's list, keeping only days that are on", () => {
    const week = monFri();
    expect(windowsFrom(week)).toHaveLength(10);
    week[0]!.on = false;
    expect(windowsFrom(week).some((w) => w.weekday === 0)).toBe(false);
  });

  it("summarises like the design says", () => {
    expect(summarise(monFri(), "WAT")).toBe("Mon to Fri, 10:00 to 12:00 and 15:00 to 17:00 WAT");
    const week = monFri();
    week[5] = { on: true, ranges: [{ start: "09:00", end: "11:00" }] };
    expect(summarise(week, "WAT")).toBe("Mon to Fri, 10:00 to 12:00 and 15:00 to 17:00 WAT; Sat, 09:00 to 11:00 WAT");
    expect(summarise(emptyWeek())).toBe("No times set yet.");
  });

  it("copies a day to weekdays or to every day, leaving the source alone", () => {
    const week = emptyWeek();
    week[0] = { on: true, ranges: [{ start: "09:00", end: "12:00" }] };
    const weekdays = copyDay(week, 0, WEEKDAYS);
    expect(weekdays.slice(0, 5).every((d) => d.on && d.ranges[0]!.start === "09:00")).toBe(true);
    expect(weekdays[5]!.on).toBe(false);
    expect(copyDay(week, 0, ALL_DAYS).every((d) => d.on)).toBe(true);
    weekdays[1]!.ranges[0]!.start = "10:00"; // copies are independent
    expect(weekdays[0]!.ranges[0]!.start).toBe("09:00");
  });

  it("applies a preset to the days that are on, or to weekdays when none are", () => {
    const fresh = applyPreset(emptyWeek(), PRESETS.mornings);
    expect(fresh.map((d) => d.on)).toEqual([true, true, true, true, true, false, false]);
    const week = emptyWeek();
    week[6] = { on: true, ranges: [] };
    const sunday = applyPreset(week, PRESETS.evenings);
    expect(sunday[6]!.ranges).toEqual([PRESETS.evenings]);
    expect(sunday[0]!.on).toBe(false);
    const twice = applyPreset(sunday, PRESETS.evenings);
    expect(twice[6]!.ranges).toHaveLength(1); // an overlapping preset is not added again
  });

  it("explains what is wrong with a day", () => {
    expect(dayProblem({ on: false, ranges: [] })).toBe("");
    expect(dayProblem({ on: true, ranges: [] })).toMatch(/Add a time range/);
    expect(dayProblem({ on: true, ranges: [{ start: "12:00", end: "09:00" }] })).toMatch(/end after it starts/);
    expect(dayProblem({ on: true, ranges: [{ start: "09:00", end: "09:10" }] })).toMatch(/at least 30 minutes/);
    expect(dayProblem({ on: true, ranges: [{ start: "09:00", end: "11:00" }, { start: "10:30", end: "12:00" }] })).toMatch(/not overlap/);
    expect(dayProblem({ on: true, ranges: [{ start: "09:00", end: "11:00" }, { start: "11:00", end: "12:00" }] })).toBe("");
    expect(hasRanges(emptyWeek())).toBe(false);
  });

  it("turns typed prices into the smallest unit and back", () => {
    expect(toMinor("20000")).toBe(2_000_000);
    expect(toMinor("20,000.50")).toBe(2_000_050);
    expect(toMinor("0")).toBeNull();
    expect(toMinor("abc")).toBeNull();
    expect(fromMinor(2_000_050)).toBe("20000.5");
    expect(fromMinor(null)).toBe("");
  });
});
