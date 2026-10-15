import { expect, test } from "@playwright/test";
import { signIn, watchConsole } from "./helpers";

const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/${name}.png` });
};

test.describe("the member area", () => {
  test("the launch toolkit sits above the directory, which opens on members", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    const labels = await nav.getByRole("link").allInnerTexts();
    const at = (label: string) => labels.findIndex((l) => l.trim() === label);
    expect(at("Launch toolkit")).toBeGreaterThan(-1);
    expect(at("Launch toolkit")).toBeLessThan(at("Directory"));
    await page.goto("/app/directory");
    await expect(page.getByRole("tab", { name: "Members", selected: true })).toBeVisible();
    await expect(page.locator('a[href^="/app/members/"]').first()).toBeVisible();
    await page.getByRole("tab", { name: "Startups" }).click();
    await expect(page).toHaveURL(/tab=startups/);
    expect(problems).toEqual([]);
  });

  test("a member can talk to Onyeka from any page and start over", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    const launcher = page.getByRole("button", { name: "Ask Onyeka" });
    await expect(launcher).toBeVisible();
    await launcher.click();
    const panel = page.getByRole("dialog", { name: "Onyeka" });
    await expect(panel).toBeVisible();
    // Begin from an empty conversation, whatever an earlier run left.
    const startOver = panel.getByRole("button", { name: "Start over" });
    if (await startOver.isVisible()) await startOver.click();
    await expect(panel.getByText("AI advisor").first()).toBeVisible();
    await expect(panel.getByText(/I'm Onyeka, founder of WO Community/)).toBeVisible();
    await shot(page, "onyeka-open");

    await panel.getByRole("button", { name: "How do I validate my idea before building?" }).click();
    await expect(panel.locator('.onyeka-msg[data-author="user"]')).toHaveCount(1);
    await expect(panel.locator('.onyeka-msg[data-author="assistant"]')).toHaveCount(2, { timeout: 20_000 });

    await panel.getByLabel("Message Onyeka").fill("What should I focus on this week?");
    await panel.getByLabel("Message Onyeka").press("Enter");
    await expect(panel.locator('.onyeka-msg[data-author="assistant"]')).toHaveCount(3, { timeout: 20_000 });
    await shot(page, "onyeka-chat");

    // The conversation is kept across pages, and the panel stays open.
    await page.goto("/app/feed");
    await expect(page.getByRole("dialog", { name: "Onyeka" }).locator('.onyeka-msg[data-author="user"]')).toHaveCount(2);

    await page.getByRole("button", { name: "Start over" }).click();
    await expect(page.getByRole("dialog", { name: "Onyeka" }).locator('.onyeka-msg[data-author="user"]')).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Onyeka" })).toHaveCount(0);
    await expect(launcher).toBeFocused();
    expect(problems).toEqual([]);
  });

  test("advice Onyeka must not give is declined", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Ask Onyeka" }).click();
    const panel = page.getByRole("dialog", { name: "Onyeka" });
    await panel.getByLabel("Message Onyeka").fill("Is it legal to lend money without a licence?");
    await panel.getByRole("button", { name: "Send" }).click();
    await expect(panel.getByText(/cannot give legal, tax or investment advice/)).toBeVisible();
    await page.getByRole("button", { name: "Start over" }).click();
    await page.getByRole("button", { name: "Close chat" }).first().click();
  });
});
