import { expect, test } from "@playwright/test";
import { PASSWORD, signIn, signInAdmin } from "./helpers";

test.describe("the public website", () => {
  test("visitors see at most ten members and startups, then an invitation to join", async ({ page }) => {
    await page.goto("/explore?tab=founders");
    const cards = page.locator(".app-grid > *");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeLessThanOrEqual(10);
    const api = await page.request.get("/api/v1/public/founders");
    if ((await api.json()).has_more) {
      await expect(page.getByRole("heading", { name: "You’re seeing 10 members. Join to see them all." })).toBeVisible();
      await expect(page.getByRole("region", { name: "See all members" }).getByRole("link", { name: "Become a member" })).toHaveAttribute("href", "/register");
    }
    expect((await page.request.get("/api/v1/public/founders?limit=11")).status()).toBe(400);
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
