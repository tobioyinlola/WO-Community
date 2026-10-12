import { expect, test, type Page } from "@playwright/test";
import { signIn, watchConsole } from "./helpers";

test.describe.configure({ mode: "serial" });

// The AI features use the back end's fake provider in the demo setup, so the answers are
// predictable enough to check the screens without calling a real service.
const NAME = `E2E venture ${Date.now()}`;
const LONG = "We help small farmers in Kaduna sell to restaurants in Lagos without middlemen.";

/** Earlier runs that stopped half way leave ventures behind, and an account may only hold three. */
async function clearOldVentures(page: Page) {
  await page.goto("/app/launch");
  await expect(page.getByRole("heading", { level: 1, name: "Launch toolkit" })).toBeVisible();
  for (;;) {
    await expect(page.getByRole("link", { name: /Active|Archived/ }).or(page.getByText("Start your first venture")).first()).toBeVisible();
    const old = page.getByRole("link", { name: /E2E (venture|look)/ });
    const before = await old.count();
    if (before === 0) return;
    await old.first().click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("button", { name: "Delete venture" }).click();
    await expect(page).toHaveURL(/\/app\/launch$/);
    await expect(old).toHaveCount(before - 1);
  }
}

async function openVenture(page: Page) {
  await signIn(page);
  await page.goto("/app/launch");
  await page.getByRole("link", { name: new RegExp(NAME) }).click();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
}

test.describe("the launch toolkit", () => {
  test("a venture can be started and the profile saved", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    await clearOldVentures(page);
    await page.getByRole("button", { name: "Start a venture" }).first().click();
    await page.getByLabel("What is it called?").fill(NAME);
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();

    await page.getByLabel("The idea in a few sentences").fill(LONG);
    await page.getByLabel("The problem", { exact: true }).fill(`${LONG} They lose a third of their harvest to delays.`);
    await page.getByLabel("Your solution").fill(`${LONG} We collect, grade and deliver within a day.`);
    await page.getByRole("button", { name: "Subscription" }).click();
    await page.getByRole("button", { name: "Africa", exact: true }).click();
    await page.getByRole("button", { name: /^Save \d+ changes?$/ }).click();
    await expect(page.getByText("Profile saved")).toBeVisible();
    await expect(page.getByRole("button", { name: "Saved" })).toBeDisabled();
    expect(problems).toEqual([]);
  });

  test("the idea can be scored and the report read", async ({ page }) => {
    const problems = watchConsole(page);
    await openVenture(page);
    await page.getByRole("link", { name: "Score", exact: true }).click();
    await page.getByRole("button", { name: "Score my idea" }).click();
    await expect(page.getByText("Overall", { exact: true })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: "How each area did" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a forecast can be started and its assumptions saved", async ({ page }) => {
    const problems = watchConsole(page);
    await openVenture(page);
    await page.getByRole("link", { name: "Forecast", exact: true }).click();
    await page.getByRole("button", { name: "Start the forecast" }).click();
    await expect(page.getByRole("heading", { name: "Your assumptions" })).toBeVisible();
    await page.getByLabel("Marketing each month").fill("50000");
    await page.getByRole("button", { name: "Save and recalculate" }).click();
    await expect(page.getByText("Forecast saved")).toBeVisible();
    await expect(page.getByText("Year 1 revenue")).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a business plan can be written and a section opened", async ({ page }) => {
    const problems = watchConsole(page);
    await openVenture(page);
    await page.getByRole("link", { name: "Business plan" }).click();
    await page.getByRole("button", { name: "Write my plan" }).click();
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible({ timeout: 90_000 });
    await page.getByRole("button", { name: /^1\./ }).click();
    await expect(page.getByRole("button", { name: "Save this section" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a pitch deck and a prototype can be made", async ({ page }) => {
    const problems = watchConsole(page);
    await openVenture(page);
    await page.getByRole("link", { name: "Pitch decks" }).click();
    await page.getByRole("button", { name: "Create deck" }).click();
    await expect(page.getByRole("navigation", { name: "Slides" })).toBeVisible();
    await page.getByRole("button", { name: "All decks" }).click();
    await page.getByRole("link", { name: "Prototypes" }).click();
    await page.getByRole("button", { name: "Create prototype" }).click();
    await expect(page.getByRole("group", { name: "Screens" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a shared link opens for someone who is signed out", async ({ page, browser }) => {
    await openVenture(page);
    await page.getByRole("link", { name: "Sharing" }).click();
    await page.getByRole("button", { name: "Create link" }).click();
    const link = await page.locator("code").first().innerText();
    expect(link).toContain("/share/");
    const visitor = await browser.newContext();
    const open = await visitor.newPage();
    await open.goto(link);
    await expect(open.getByRole("heading", { level: 1 })).toBeVisible();
    await visitor.close();
    await page.getByRole("button", { name: "Turn off" }).first().click();
    await expect(page.getByText("Turned off").first()).toBeVisible();
  });

  test("the venture partner answers and the venture can be deleted", async ({ page }) => {
    await openVenture(page);
    await page.getByRole("link", { name: "Partner" }).click();
    await page.getByRole("button", { name: "New conversation" }).click();
    await page.getByLabel("Ask the venture partner").fill("What should I do first?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Venture partner").first()).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("button", { name: "Delete venture" }).click();
    await expect(page).toHaveURL(/\/app\/launch$/);
  });
});
