import { describe, expect, it } from "vitest";
import { fromLocalInput, toLocalInput } from "./zoned";

describe("zoned times", () => {
  it("reads a clock time in Lagos as one hour behind in UTC", () => {
    expect(fromLocalInput("2026-10-10T15:00", "Africa/Lagos")).toBe("2026-10-10T14:00:00.000Z");
  });

  it("reads a clock time in Johannesburg as two hours behind in UTC", () => {
    expect(fromLocalInput("2026-10-10T09:30", "Africa/Johannesburg")).toBe("2026-10-10T07:30:00.000Z");
  });

  it("allows for summer time in zones that have it", () => {
    expect(fromLocalInput("2026-07-01T09:00", "America/New_York")).toBe("2026-07-01T13:00:00.000Z");
    expect(fromLocalInput("2026-01-15T09:00", "America/New_York")).toBe("2026-01-15T14:00:00.000Z");
  });

  it("shows a moment on the clock of the zone it is in", () => {
    expect(toLocalInput("2026-10-10T14:00:00Z", "Africa/Lagos")).toBe("2026-10-10T15:00");
    expect(toLocalInput("2026-10-10T23:30:00Z", "Africa/Nairobi")).toBe("2026-10-11T02:30");
  });

  it("round trips what a person types", () => {
    for (const zone of ["Africa/Lagos", "Africa/Cairo", "UTC"]) {
      expect(toLocalInput(fromLocalInput("2026-03-29T01:30", zone), zone)).toBe("2026-03-29T01:30");
    }
  });

  it("gives an empty field for an empty value", () => {
    expect(toLocalInput("", "Africa/Lagos")).toBe("");
  });
});
