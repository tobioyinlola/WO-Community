import { expect, test } from "@playwright/test";
import { PASSWORD, signIn, signInAdmin } from "./helpers";

test.describe("the public website", () => {
  test("visitors see at most twelve members, by first name and last initial, then an invitation to join", async ({ page }) => {
    await page.goto("/explore?tab=founders");
    const cards = page.locator(".app-grid > *");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeLessThanOrEqual(12);
    // Every name is a first name and an initial ("Amaka O."), never a full name.
    for (const name of await cards.locator("h3").allInnerTexts()) expect(name).toMatch(/^\S+( \p{L}\.)?$/u);
    const api = await page.request.get("/api/v1/public/founders");
    if ((await api.json()).has_more) {
      await expect(page.getByRole("heading", { name: "You’re seeing 12 members. Join to see them all." })).toBeVisible();
      await expect(page.getByRole("region", { name: "See all members" }).getByRole("link", { name: "Become a member" })).toHaveAttribute("href", "/register");
    }
    expect((await page.request.get("/api/v1/public/founders?limit=13")).status()).toBe(400);
  });

  test("the public cards line up in every row and nothing scrolls sideways, on a phone or a desktop", async ({ page }) => {
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const tab of ["startups", "founders", "courses"]) {
        await page.goto(`/explore?tab=${tab}`);
        await expect(page.locator(".app-grid > *").first()).toBeVisible();
        const shape = await page.evaluate(() => {
          const rows: Record<number, Set<number>> = {};
          for (const card of document.querySelectorAll(".app-grid > *")) {
            const box = card.getBoundingClientRect();
            (rows[Math.round(box.top)] ??= new Set()).add(Math.round(box.height));
          }
          const root = document.documentElement;
          return { unevenRows: Object.values(rows).filter((heights) => heights.size > 1).length, sideways: root.scrollWidth > root.clientWidth };
        });
        expect(shape, `${tab} at ${width}px`).toEqual({ unevenRows: 0, sideways: false });
      }
    }
  });

  test("visitors browse the courses, and opening one asks them to join", async ({ page }) => {
    await page.goto("/explore?tab=courses");
    const card = page.locator("a.explore-course").first();
    await expect(card).toBeVisible();
    await expect(card).toContainText("Join to open this course");
    await card.click();
    await expect(page).toHaveURL(/\/p\/course\//);
    await expect(page.getByRole("link", { name: /become a member/i }).first()).toBeVisible();
  });

  test("anyone can sign up for the newsletter in the footer", async ({ page }) => {
    await page.goto("/");
    const footer = page.locator("footer");
    await footer.getByRole("button", { name: "Subscribe" }).click();
    await expect(footer.getByText("Enter a full email address.")).toBeVisible();
    await footer.getByLabel("Email address").fill(`reader.${Date.now()}@example.com`);
    await footer.getByRole("button", { name: "Subscribe" }).click();
    await expect(footer.getByText("Almost there. Check your inbox")).toBeVisible();
  });

  test("a bad newsletter link says so", async ({ page }) => {
    await page.goto("/newsletter/confirm?token=not-a-real-link");
    await expect(page.getByText("This link did not work")).toBeVisible();
  });

  test("the sign up form asks for LinkedIn and the company website", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(`linked.${Date.now()}@demo.test`);
    await page.getByLabel("Password", { exact: true }).fill("a-long-passphrase-2026");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Full name").fill("Linked Applicant");
    await page.getByLabel("Country").selectOption({ label: "Nigeria" });
    await page.getByLabel("City").fill("Lagos");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Add the link to your LinkedIn profile")).toBeVisible();
    await page.getByLabel("LinkedIn profile").fill("linkedin.com/in/linked-applicant");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Company name").fill("Linked Labs");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Add your company website")).toBeVisible();
  });
});

test.describe("the leaderboard", () => {
  test("members see the top members and how points work", async ({ page }) => {
    await signIn(page);
    await expect(page.getByRole("heading", { name: "Top members this month" })).toBeVisible();
    await page.getByRole("link", { name: "Leaderboard" }).first().click();
    await expect(page).toHaveURL(/\/app\/leaderboard/);
    await expect(page.getByRole("heading", { level: 1, name: "Leaderboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "How points work" })).toBeVisible();
    await expect(page.getByText("Post in the feed")).toBeVisible();
  });

  test("admins see the most engaged members on the dashboard", async ({ page }) => {
    await signInAdmin(page);
    await expect(page.getByRole("heading", { name: "Most engaged members" })).toBeVisible();
  });
});

test.describe("admin sign in", () => {
  test("after entering the code, signing in again the same day needs only the password", async ({ page }) => {
    await signInAdmin(page);
    await page.getByRole("button", { name: /Account menu/ }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login|\/$/);

    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@demo.test");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    // Straight in, with no code asked for.
    await expect(page).toHaveURL(/\/(app|admin)/);
    await expect(page.getByRole("heading", { name: "Enter your code" })).toHaveCount(0);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  });

  test("another browser still asks for the code", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@demo.test");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Enter your code" })).toBeVisible();
    await context.close();
  });
});
