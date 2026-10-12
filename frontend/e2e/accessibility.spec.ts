import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

/**
 * Every screen is checked at the four widths in the definition of done, in both themes at the
 * narrowest and widest, for WCAG 2.2 AA rules an automated tool can judge and for sideways scroll.
 * It does not replace trying the app with a screen reader.
 */
const PUBLIC = ["/", "/explore", "/news", "/login", "/register", "/forgot-password", "/legal/terms"];
const MEMBER = ["/app", "/app/feed", "/app/directory", "/app/jobs", "/app/jobs/new", "/app/events", "/app/learn", "/app/mentors", "/app/mentors/sessions", "/app/news", "/app/notifications", "/app/me", "/app/settings", "/app/launch"];
const TABS = ["", "/profile", "/score", "/plan", "/forecast", "/decks", "/prototypes", "/partner", "/sharing"];
const COMBOS = [
  { width: 360, height: 780, scheme: "light" },
  { width: 360, height: 780, scheme: "dark" },
  { width: 768, height: 1024, scheme: "light" },
  { width: 1024, height: 768, scheme: "light" },
  { width: 1280, height: 800, scheme: "light" },
  { width: 1280, height: 800, scheme: "dark" },
] as const;

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

async function audit(page: Page, path: string, label: string, problems: string[]) {
  await page.goto(path);
  // The pages poll for notifications, so the network never goes quiet; wait for the content instead.
  await expect(page.locator("main, [role=main]").first()).toBeVisible();
  await page.waitForTimeout(900);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) problems.push(`${label} ${path}: scrolls sideways by ${overflow}px`);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  for (const v of result.violations) {
    problems.push(`${label} ${path}: ${v.id} (${v.impact}) on ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
  }
}

async function ventureBase(page: Page): Promise<string> {
  await page.goto("/app/launch");
  const card = page.getByRole("link", { name: /E2E look/ });
  await expect(card.or(page.getByText("Start your first venture")).first()).toBeVisible();
  if ((await card.count()) === 0) {
    await page.getByRole("button", { name: "Start a venture" }).first().click();
    await page.getByLabel("What is it called?").fill("E2E look");
    await page.getByRole("button", { name: "Create" }).click();
  } else {
    await card.first().click();
  }
  await expect(page.getByRole("heading", { level: 1, name: "E2E look" })).toBeVisible();
  return page.url().replace(/\/(profile|score|plan|forecast|decks|prototypes|partner|sharing)$/, "");
}

for (const { width, height, scheme } of COMBOS) {
  test(`${width}px wide, ${scheme} theme`, async ({ browser }) => {
    const label = `${width}px ${scheme}`;
    const problems: string[] = [];
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
    const page = await context.newPage();
    for (const path of PUBLIC) await audit(page, path, label, problems);
    await signIn(page);
    for (const path of MEMBER) await audit(page, path, label, problems);
    const base = await ventureBase(page);
    for (const tab of TABS) await audit(page, base + tab, label, problems);
    await context.close();
    expect(problems).toEqual([]);
  });
}

const ADMIN_PAGES = ["/admin", "/admin/members", "/admin/invitations", "/admin/mentors", "/admin/reports", "/admin/jobs", "/admin/wins", "/admin/news", "/admin/events", "/admin/courses", "/admin/email", "/admin/lists", "/admin/security"];

for (const { width, height, scheme } of [COMBOS[1], COMBOS[2], COMBOS[4]]) {
  test(`admin console, ${width}px wide, ${scheme} theme`, async ({ browser }) => {
    const label = `admin ${width}px ${scheme}`;
    const problems: string[] = [];
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
    const page = await context.newPage();
    await signInAdmin(page);
    for (const path of ADMIN_PAGES) await audit(page, path, label, problems);
    await context.close();
    expect(problems).toEqual([]);
  });
}

test("the audit venture is removed", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/launch");
  const card = page.getByRole("link", { name: /E2E look/ });
  await expect(card.or(page.getByText("Start your first venture"))).toBeVisible();
  if ((await card.count()) > 0) {
    await card.first().click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("button", { name: "Delete venture" }).click();
    await expect(page).toHaveURL(/\/app\/launch$/);
  }
});
