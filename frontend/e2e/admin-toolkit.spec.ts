import { expect, test } from "@playwright/test";
import { signInAdmin, watchConsole } from "./helpers";

test.describe.configure({ mode: "serial" });

const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/${name}.png`, fullPage: true });
};

test.describe("the toolkit admin pages", () => {
  test("every toolkit page opens and shows its content", async ({ page }) => {
    const problems = watchConsole(page);
    await signInAdmin(page);

    await page.goto("/admin/toolkit/ventures");
    await expect(page.getByRole("heading", { level: 1, name: "Ventures" })).toBeVisible();
    await expect(page.getByText("With a business plan")).toBeVisible();
    await page.getByLabel("Venture name or owner email").fill("no-such-venture-zzz");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText("No venture matches")).toBeVisible();
    await page.getByLabel("Venture name or owner email").fill("");
    await page.getByRole("button", { name: "Search" }).click();
    await shot(page, "admin-tk-ventures");

    await page.goto("/admin/toolkit/templates");
    await expect(page.getByRole("heading", { level: 1, name: "Templates" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Pitch deck templates" })).toBeVisible();
    await shot(page, "admin-tk-templates-decks");
    for (const tab of await page.getByRole("tab").all()) {
      await tab.click();
      await expect(page.getByRole("tabpanel")).toBeVisible();
    }
    await expect(page.getByRole("heading", { name: "Business plan sections" })).toBeVisible();
    await shot(page, "admin-tk-templates-plan");
    await page.getByRole("button", { name: "Edit" }).nth(1).click();
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Section saved")).toBeVisible();

    await page.goto("/admin/toolkit/rubric");
    await expect(page.getByRole("heading", { level: 1, name: "Scoring rubric" })).toBeVisible();
    await expect(page.getByText("Versions are kept")).toBeVisible();
    await shot(page, "admin-tk-rubric");
    await page.getByRole("button", { name: "New version" }).click();
    const dialog = page.getByRole("dialog");
    const json = dialog.getByLabel("Rubric (JSON)");
    const original = await json.inputValue();
    await json.fill("{ not json");
    await dialog.getByRole("button", { name: "Add version" }).click();
    await expect(dialog.getByText(/JSON|valid/i).first()).toBeVisible();
    await json.fill(original);
    await dialog.getByLabel("What changed (optional)").fill("Checked by the end to end test");
    await dialog.getByRole("button", { name: "Add version" }).click();
    await expect(page.getByText(/added\. Make it active to use it/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Make active" }).first()).toBeVisible();

    await page.goto("/admin/toolkit/usage");
    await expect(page.getByRole("heading", { level: 1, name: "AI usage" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "How the toolkit is set up" })).toBeVisible();
    await page.getByLabel("Group by").selectOption("prompt");
    await shot(page, "admin-tk-usage");

    await page.goto("/admin/toolkit/quality");
    await expect(page.getByRole("heading", { level: 1, name: "Quality queue" })).toBeVisible();
    await expect(page.getByText(/Nothing to look at|Answers that worked/).first()).toBeVisible();
    await shot(page, "admin-tk-quality");

    expect(problems).toEqual([]);
  });
});
