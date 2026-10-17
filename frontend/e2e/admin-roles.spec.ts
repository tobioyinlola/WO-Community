import { expect, test } from "@playwright/test";
import { signInAdmin } from "./helpers";
import { ADMIN_KEY, freshCode } from "./totp";

// The panel used to close itself, and the role dialog with it, as soon as the dialog or the fresh
// code check it asks for was used.
test("a console role is given after the fresh code check, with the panel still open", async ({ page }) => {
  await signInAdmin(page);
  let asked = false;
  await page.route("**/api/v1/admin/members/*/role", async (route) => {
    if (asked) return route.continue();
    asked = true;
    await route.fulfill({ status: 403, contentType: "application/problem+json", body: JSON.stringify({ status: 403, code: "step_up_required", detail: "Enter a fresh code." }) });
  });
  await page.goto("/admin/members");
  await page.getByRole("link", { name: "Ada Nwosu" }).click();
  const panel = page.locator(".adm-sheet");
  await page.getByRole("button", { name: "Change role" }).click();
  const role = page.getByRole("dialog", { name: "Change console role" });
  await role.getByLabel("Role").selectOption("content_editor");
  const button = role.getByRole("button", { name: /Give role|Remove role/ });
  const giving = (await button.innerText()).includes("Give");
  await button.click();
  const stepUp = page.getByRole("dialog", { name: "Confirm it is you" });
  await expect(stepUp).toBeVisible();
  await expect(role).toBeVisible();
  await expect(panel).toBeVisible();
  await stepUp.getByLabel("Authenticator code").fill(await freshCode(ADMIN_KEY, true));
  await stepUp.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(giving ? "Role given" : "Role removed")).toBeVisible();
  await expect(role).toHaveCount(0);
  await expect(panel).toBeVisible();

  // Put it back as it was. The code was just confirmed, so no second check is asked for.
  await page.getByRole("button", { name: "Change role" }).click();
  await role.getByLabel("Role").selectOption("content_editor");
  await role.getByRole("button", { name: giving ? "Remove role" : "Give role" }).click();
  await expect(page.getByText(giving ? "Role removed" : "Role given")).toBeVisible();
  await expect(panel).toBeVisible();
});
