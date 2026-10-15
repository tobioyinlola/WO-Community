import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

// Tunde is a member who is not a mentor and has not applied, with a startup from the demo data.
const FOUNDER = "tunde@demo.test";

test.describe("mentor application", () => {
  test("problems are named under each field, and a complete application is sent", async ({ page }) => {
    await signIn(page, FOUNDER);
    await page.goto("/app/mentors/become");
    await page.getByLabel("I will follow the mentor code of conduct").check();
    await page.getByRole("button", { name: "Send application" }).click();

    await expect(page.getByText("Some answers need fixing")).toBeVisible();
    await expect(page.getByText("Choose at least one industry.")).toBeVisible();
    await expect(page.getByText("Choose at least one stage.")).toBeVisible();
    await expect(page.getByText(/Paste the full address of your LinkedIn profile/)).toBeVisible();

    await page.getByLabel("Your areas of expertise").fill("fundraising, hiring");
    await page.getByLabel("Years of experience").fill("8");
    await page.getByLabel("Current role").fill("Partner");
    await page.getByLabel("Company").fill("Delta Capital");
    await page.getByLabel("LinkedIn profile").fill("linkedin.com/in/tunde-kolade");
    await page.getByRole("button", { name: "Fintech", exact: true }).click();
    await page.getByRole("button", { name: "Seed", exact: true }).click();
    await page.getByLabel("Why do you want to mentor?").fill("I have raised three rounds and want to help founders avoid the mistakes I made.");
    await page.getByRole("button", { name: "Send application" }).click();

    await expect(page.getByText("Your application has been received")).toBeVisible();
    await expect(page.getByText(/within 3 to 5 working days/)).toBeVisible();
  });
});

test.describe("profile", () => {
  test("About you counts words and characters and flags going over", async ({ page }) => {
    await signIn(page, FOUNDER);
    await page.goto("/app/me");
    const about = page.getByLabel("About you");
    await about.fill("I build payments for small traders");
    await expect(page.getByText("6 words · 34/500 characters")).toBeVisible();
    await about.fill("word ".repeat(110));
    await expect(page.getByText(/characters too long/)).toBeVisible();
  });

  test("the photo card offers an upload and turns away a file that is not an image", async ({ page }) => {
    await signIn(page, FOUNDER);
    await page.goto("/app/me");
    await expect(page.getByRole("heading", { name: "Your photo" })).toBeVisible();
    await page.locator('input[type="file"]').setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
    await expect(page.getByText("Choose a JPEG, PNG or WebP image.")).toBeVisible();
  });
});

test.describe("traction", () => {
  test("traction is saved on the startup and shows in the directory", async ({ page }) => {
    await signIn(page, FOUNDER);
    await page.goto("/app/me");
    await page.getByRole("link", { name: "Delta Capital" }).click();
    const startupUrl = page.url();
    await page.goto(`${startupUrl}/edit#traction`);
    await expect(page.getByRole("heading", { name: "Traction" })).toBeVisible();
    await page.getByLabel("Users or customers").fill("1200");
    await page.getByLabel("Funding raised").selectOption("250k_1m");
    await page.getByRole("button", { name: "Add milestone" }).click();
    await page.getByLabel("Milestones 1").fill("Opened a Lagos office");
    await page.getByRole("button", { name: "Save traction" }).click();
    await expect(page.getByText("Traction saved")).toBeVisible();

    await page.goto(startupUrl);
    await expect(page.getByText("Opened a Lagos office")).toBeVisible();
  });
});
