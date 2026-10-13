import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * The public landing page: its content is all still there, nothing scrolls sideways at any width,
 * text keeps its contrast in both themes, and the page can be used from the keyboard and with
 * reduced motion.
 */
const WIDTHS = [360, 768, 1024, 1280, 1536] as const;

async function open(page: Page, theme: "light" | "dark" = "light") {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // The app is light only; the dark tokens are applied directly to check the dark styles.
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await showEverything(page);
}

/** Scrolls down in steps so every section has been revealed, then back to the top. */
async function showEverything(page: Page) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < height; y += 350) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(80);
  }
  await page.waitForTimeout(900);
  await page.evaluate(() => window.scrollTo(0, 0));
}

test("the landing page keeps its sections, copy and links", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("The future of Africa is being built here.");
  for (const name of ["Everything a founder needs, in one place", "Built for people who build", "Coming up", "From the community"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  for (const name of ["Find your people", "Learn from people who did it", "Launch with a plan", "Keep learning", "Hire and get hired", "Meet in person"]) {
    await expect(page.getByRole("heading", { level: 3, name })).toBeVisible();
  }
  await expect(page.getByRole("heading", { level: 3, name: "Every member is reviewed" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Request access/ }).first()).toHaveAttribute("href", "/register");
  await expect(page.getByRole("link", { name: "Sign in" }).first()).toHaveAttribute("href", "/login");
  // The big wordmark in the footer is decoration, not content.
  await expect(page.locator(".site-footer__mark")).toHaveAttribute("aria-hidden", "true");
});

for (const width of WIDTHS) {
  test(`no sideways scroll at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await open(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [360, 1440]) {
    test(`contrast and accessibility, ${theme}, ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page, theme);
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      const found = result.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
      expect(found).toEqual([]);
    });
  }
}

test("the header floats, then blurs once the page has moved", async ({ page }) => {
  await page.goto("/");
  const head = page.locator("nav.site-head");
  await expect(head).toHaveAttribute("data-scrolled", "false");
  await page.evaluate(() => window.scrollTo(0, 400));
  await expect(head).toHaveAttribute("data-scrolled", "true");
  await expect(head).toBeInViewport();
});

test("the mobile menu opens and closes from the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/");
  const button = page.getByRole("button", { name: "Open menu" });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("link", { name: "Explore" }).first()).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
});

test("every control can be reached with Tab and shows a focus ring", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const reached: string[] = [];
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      return { text: (el.textContent ?? el.getAttribute("aria-label") ?? "").trim().slice(0, 30), ring: style.boxShadow !== "none" || style.outlineStyle !== "none" };
    });
    if (info) {
      reached.push(info.text);
      expect(info.ring, `focus ring on "${info.text}"`).toBe(true);
    }
  }
  expect(reached).toEqual(expect.arrayContaining(["Home", "Explore", "News", "Sign in"]));
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("everything is shown at once and nothing animates", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 3, name: "Meet in person" })).toBeVisible();
    // No card waits for a scroll to appear.
    const pending = await page.locator(".reveal[data-reveal='pending']").count();
    expect(pending).toBe(0);
    const drawn = await page.locator(".site-hero__line path").first().evaluate((el) => getComputedStyle(el).strokeDashoffset);
    expect(parseFloat(drawn)).toBe(0);
    const animated = await page.locator(".site-hero__line path").first().evaluate((el) => getComputedStyle(el).animationName);
    expect(animated).toBe("none");
  });
});
