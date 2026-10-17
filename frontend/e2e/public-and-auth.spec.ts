import { expect, test } from "@playwright/test";
import { MEMBER, PASSWORD, PENDING, signIn, watchConsole } from "./helpers";

test.describe("public site", () => {
  test("the landing page shows the brand headline with one highlighted word", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    const headline = page.getByRole("heading", { level: 1 });
    await expect(headline).toContainText("African entrepreneurship is built here together.");
    await expect(headline.locator(".wo-hl")).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Request access" }).first()).toBeVisible();
    // Real data from the public API: a seeded event and a seeded news item.
    await expect(page.getByText("Demo Day, Lagos")).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("explore lists public startups, then jobs", async ({ page }) => {
    await page.goto("/explore");
    await expect(page.getByText("Kuda Foods")).toBeVisible();
    await page.getByRole("tab", { name: "Jobs" }).click();
    await expect(page.getByText("Senior backend engineer")).toBeVisible();
  });

  test("a news story opens", async ({ page }) => {
    await page.goto("/news");
    await page.getByRole("link", { name: /Kuda Foods raises a seed round/ }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Kuda Foods raises a seed round");
  });
});

test.describe("signing in", () => {
  test("visitors are sent to sign in and brought back afterwards", async ({ page }) => {
    await page.goto("/app/feed");
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email").fill(MEMBER);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/app\/feed/);
  });

  test("a wrong password shows the server's message and keeps the form", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(MEMBER);
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText("Invalid email or password");
    await expect(page).toHaveURL(/\/login/);
  });

  test("an unconfirmed email is told to confirm first", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("unverified@demo.test");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Confirm your email first" })).toBeVisible();
  });

  test("the session survives a reload and ends on sign out", async ({ page }) => {
    await signIn(page);
    await page.reload();
    await expect(page).toHaveURL(/\/app/);
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
  });

  test("a member awaiting approval sees the holding page, not the community", async ({ page }) => {
    await signIn(page, PENDING);
    await expect(page.getByRole("heading", { name: "Thank you for applying" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Feed" })).toHaveCount(0);
  });
});

test.describe("requesting access", () => {
  test("the form walks through four steps and checks each one", async ({ page }) => {
    await page.goto("/register");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Enter a full email address.")).toBeVisible();
    await page.getByLabel("Email").fill(`new.${Date.now()}@demo.test`);
    await page.getByLabel("Password", { exact: true }).fill("a-long-passphrase-2026");
    await page.getByRole("button", { name: "Continue" }).click();

    await page.getByLabel("Full name").fill("Test Applicant");
    await page.getByLabel("Country").selectOption({ label: "Nigeria" });
    await page.getByLabel("City").fill("Lagos");
    await page.getByLabel("LinkedIn profile").fill("linkedin.com/in/new-member");
    await page.getByRole("button", { name: "Continue" }).click();

    await page.getByLabel("Company name").fill("Applicant Labs");
    await page.getByLabel("Company website").fill("newcompany.example.com");
    await page.getByLabel("Sector").selectOption({ label: "Fintech" });
    await page.getByLabel("Stage").selectOption({ index: 1 });
    await page.getByLabel("What does it do?").fill("Payments for small shops.");
    await page.getByRole("button", { name: "Continue" }).click();

    await page.getByRole("button", { name: "Request access" }).click();
    await expect(page.getByText("Accept the terms to continue.")).toBeVisible();
    await page.getByLabel(/I accept the\s+terms/).check();
    await page.getByLabel(/privacy policy/).check();
    await page.getByLabel(/code of conduct/).check();
    await page.getByRole("button", { name: "Request access" }).click();
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await expect(page.getByText("Application received")).toBeVisible();
  });
});
