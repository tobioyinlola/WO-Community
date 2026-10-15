import { welcomeTitle } from "./greeting";

const at = (hour: number) => new Date(2026, 9, 15, hour, 30);

describe("welcomeTitle", () => {
  it("greets by the time of day", () => {
    expect(welcomeTitle("Ada", at(8))).toBe("Good morning, Ada ☀️");
    expect(welcomeTitle("Ada", at(13))).toBe("Good afternoon, Ada 🌤️");
    expect(welcomeTitle("Ada", at(19))).toBe("Good evening, Ada 🌙");
    expect(welcomeTitle("Ada", at(2))).toBe("Good evening, Ada 🌙");
  });

  it("works without a name", () => {
    expect(welcomeTitle("", at(8))).toBe("Good morning ☀️");
  });
});
