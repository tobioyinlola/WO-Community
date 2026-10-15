import { expect, test } from "@playwright/test";
import { signIn, watchConsole } from "./helpers";

// Runs when the API has no AI service (AI_PROVIDER blank), as production does until a key is set.
// Every tool must still work, and the AI-only buttons must be out of the way.
test.describe.configure({ mode: "serial" });

const NAME = `E2E look ${Date.now()}`;
const LONG = "We help small farmers in Kaduna sell to restaurants in Lagos without middlemen.";
const SHOTS = process.env.E2E_SHOTS ?? "";

test("with AI off, every tool still works from start to finish", async ({ page }) => {
  test.setTimeout(180_000);
  const problems = watchConsole(page);
  await signIn(page);
  await page.goto("/app/launch");
  await page.getByRole("button", { name: "Start a venture" }).first().click();
  await page.getByLabel("What is it called?").fill(NAME);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
  const off = page.getByText("AI writing is off for now");
  test.skip(!(await off.isVisible().catch(() => false)), "AI is on in this environment");

  // The partner is all AI conversation, so it is not offered; nor are the AI buttons.
  await expect(page.getByRole("link", { name: "Partner" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Fill from a few sentences" })).toHaveCount(0);
  await page.getByLabel("The idea in a few sentences").fill(LONG);
  await page.getByLabel("The problem", { exact: true }).fill(`${LONG} They lose a third of their harvest to delays.`);
  await page.getByLabel("Your solution").fill(`${LONG} We collect, grade and deliver within a day.`);
  await page.getByRole("button", { name: "Subscription" }).click();
  await page.getByRole("button", { name: "Africa", exact: true }).click();
  await page.getByRole("button", { name: /^Save \d+ changes?$/ }).click();
  await expect(page.getByText("Profile saved")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/off-profile.png`, fullPage: true });

  // The score is worked out from the answers.
  await page.getByRole("link", { name: "Score", exact: true }).click();
  await page.getByRole("button", { name: "Score my idea" }).click();
  await expect(page.getByRole("heading", { name: "How each area did" })).toBeVisible({ timeout: 60_000 });
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/off-score.png`, fullPage: true });

  // The plan is laid out section by section for the founder to write, and a section saves.
  await page.getByRole("link", { name: "Business plan" }).click();
  await page.getByRole("button", { name: "Lay out my plan" }).click();
  await page.getByRole("button", { name: /^1\./ }).click({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Ask for help with this section" })).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/off-plan.png`, fullPage: true });

  // The forecast is all calculation.
  await page.getByRole("link", { name: "Forecast", exact: true }).click();
  await page.getByRole("button", { name: "Start the forecast" }).click();
  await expect(page.getByRole("heading", { name: "Your assumptions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Suggest typical numbers" })).toHaveCount(0);
  await page.getByLabel("Marketing each month").fill("50000");
  await page.getByRole("button", { name: "Save and recalculate" }).click();
  await expect(page.getByText("Year 1 revenue")).toBeVisible();

  // Decks and prototypes start from templates.
  await page.getByRole("link", { name: "Pitch decks" }).click();
  await page.getByRole("button", { name: "Create deck" }).click();
  await expect(page.getByRole("navigation", { name: "Slides" })).toBeVisible();
  await expect(page.getByText("Reword this slide:")).toHaveCount(0);
  await page.getByRole("button", { name: "All decks" }).click();
  await page.getByRole("link", { name: "Prototypes" }).click();
  await expect(page.getByRole("heading", { name: "Draft one from your idea" })).toHaveCount(0);
  await page.getByRole("button", { name: "Create prototype" }).click();
  await expect(page.getByRole("group", { name: "Screens" })).toBeVisible();

  await page.getByRole("link", { name: "Overview" }).click();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/off-overview.png`, fullPage: true });
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Delete venture" }).click();
  await expect(page).toHaveURL(/\/app\/launch$/);
  expect(problems).toEqual([]);
});
