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
  for (const name of [
    "Everything a founder needs, in one place",
    "From request to member",
    "On your own, or in the community",
    "Built for people who build",
    "Coming up",
    "From the community",
    "Questions, answered",
  ]) {
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

test("the numbers are the real counts and each one leads to what it counts", async ({ page, request }) => {
  const counts = await (await request.get("/api/v1/public/stats")).json();
  await open(page);
  const region = page.getByRole("region", { name: "The community in numbers" }).or(page.locator("section[aria-labelledby=numbers]"));
  await expect(region).toBeVisible();
  for (const [label, key] of [["Startups listed", "startups"], ["Founders listed", "founders"], ["Open roles", "jobs"]] as const) {
    if (counts[key] > 0) {
      const tile = region.getByRole("link", { name: new RegExp(label) });
      await expect(tile.locator(".wo-visually-hidden")).toHaveText(String(counts[key]));
    }
  }
  await region.getByRole("link", { name: /Startups listed/ }).click();
  await expect(page).toHaveURL(/\/explore\?tab=startups/);
});

test("the feature cards scroll sideways with the round buttons and the arrow keys", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await open(page);
  const track = page.getByRole("list", { name: /What you get/ });
  await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  await page.getByRole("button", { name: "Next" }).click();
  await expect.poll(() => track.evaluate((el) => el.scrollLeft)).toBeGreaterThan(100);
  await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  const before = await track.evaluate((el) => el.scrollLeft);
  await track.focus();
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => track.evaluate((el) => el.scrollLeft)).toBeLessThan(before);
});

test("a feature card opens the page it is about", async ({ page }) => {
  await open(page);
  await page.getByRole("link", { name: "Explore: Hire and get hired" }).click();
  await expect(page).toHaveURL(/\/explore\?tab=jobs/);
  await expect(page.getByRole("tab", { name: "Jobs" })).toHaveAttribute("aria-selected", "true");
});

test("the questions open one at a time", async ({ page }) => {
  await open(page);
  const first = page.getByRole("button", { name: "Who can join?" });
  const second = page.getByRole("button", { name: "What happens after I request access?" });
  await expect(first).toHaveAttribute("aria-expanded", "true");
  await second.click();
  await expect(second).toHaveAttribute("aria-expanded", "true");
  await expect(first).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("An admin reviews your request and replies by email.", { exact: false })).toBeVisible();
  await expect(page.getByText("Founders, operators and investors who are building", { exact: false })).toBeHidden();
  await second.focus();
  await page.keyboard.press("Enter");
  await expect(second).toHaveAttribute("aria-expanded", "false");
});

test("there are no member quotes or social links until real ones are supplied", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: /own words/i })).toHaveCount(0);
  await expect(page.getByRole("list", { name: /social media/i })).toHaveCount(0);
});

test("the page describes itself to search engines, and robots.txt is plain text", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator("meta[name=description]")).toHaveAttribute("content", /WO Community is the members/);
  const robots = await request.get("/robots.txt");
  expect(robots.headers()["content-type"]).toContain("text/plain");
  const body = await robots.text();
  expect(body).toContain("User-agent: *");
  expect(body).toContain("Disallow: /admin");
});
