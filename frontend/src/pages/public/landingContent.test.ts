import { describe, expect, it } from "vitest";
import { COMPARE, FAQ, SOCIAL_LINKS, STEPS } from "./landingContent";

/** Guards for the words that are edited by hand: whatever is added later still has to be sound. */
describe("landing content", () => {
  it("has four steps, three pairs and a full set of answers", () => {
    expect(STEPS).toHaveLength(4);
    expect(COMPARE).toHaveLength(3);
    for (const item of FAQ) {
      expect(item.question.endsWith("?")).toBe(true);
      expect(item.answer.length).toBeGreaterThan(20);
    }
  });

  it("asks each question once", () => {
    expect(new Set(FAQ.map((i) => i.question)).size).toBe(FAQ.length);
  });

  it("holds only https addresses for social links, one per network", () => {
    for (const link of SOCIAL_LINKS) expect(link.href.startsWith("https://")).toBe(true);
    expect(new Set(SOCIAL_LINKS.map((l) => l.kind)).size).toBe(SOCIAL_LINKS.length);
  });
});
