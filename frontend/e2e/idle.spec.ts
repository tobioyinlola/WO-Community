import { expect, test } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe("signing out after inactivity", () => {
  test("a warning comes after four quiet minutes and the member is signed out at five", async ({ page }) => {
    await page.clock.install();
    await signIn(page);

    await page.clock.fastForward("04:05");
    await expect(page.getByRole("dialog", { name: "You are about to be signed out" })).toBeVisible();

    await page.clock.fastForward("01:00");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("For your security, we sign you out after 5 minutes without activity.")).toBeVisible();
  });

  test("Stay signed in keeps the session", async ({ page }) => {
    await page.clock.install();
    await signIn(page);

    await page.clock.fastForward("04:05");
    await page.getByRole("button", { name: "Stay signed in" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.clock.fastForward("02:00");
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
