import { expect, test } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe("signing out after inactivity", () => {
  test("a member is signed out after five quiet minutes, with no warning first", async ({ page }) => {
    await page.clock.install();
    await signIn(page);

    await page.clock.fastForward("04:30");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page).toHaveURL(/\/app/);

    await page.clock.fastForward("00:35");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("For your security, we sign you out after 5 minutes without activity.")).toBeVisible();
  });

  test("activity keeps the session", async ({ page }) => {
    await page.clock.install();
    await signIn(page);

    await page.clock.fastForward("04:00");
    await page.mouse.move(200, 200);
    await page.keyboard.press("Shift");
    await page.clock.fastForward("03:00");
    await expect(page).toHaveURL(/\/app/);
  });

  test("the admin console signs out the same way", async ({ page }) => {
    await page.clock.install();
    await signInAdmin(page);
    await expect(page).toHaveURL(/\/admin/);

    await page.clock.fastForward("05:05");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("You were signed out")).toBeVisible();
  });
});
