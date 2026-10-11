import { expect, test } from "@playwright/test";
import { signIn, signInAdmin, watchConsole } from "./helpers";
import { freshCode, totp } from "./totp";

test.describe.configure({ mode: "serial" });

const EDITOR = "editor@demo.test";

test.describe("the admin console", () => {
  test("a member is sent back to the community", async ({ page }) => {
    await signIn(page);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/app$/);
  });

  test("an editor must set up two step sign in before anything opens, then can use their sections", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page, EDITOR);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: "Set up two step sign in" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Admin" })).toHaveCount(0);
    const key = (await page.locator("code").first().innerText()).trim();
    await page.getByLabel("Code from the app").fill(await freshCode(key));
    await page.getByRole("button", { name: "Turn on two step sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Keep these recovery codes" })).toBeVisible();
    await page.getByRole("button", { name: "I have saved them" }).click();
    const nav = page.getByRole("navigation", { name: "Admin" });
    await expect(nav.getByRole("link", { name: "Jobs" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Members" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test("the overview shows what is waiting", async ({ page }) => {
    const problems = watchConsole(page);
    await signInAdmin(page);
    await expect(page.getByText("Waiting for approval")).toBeVisible();
    await expect(page.getByText("Open reports")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Community" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a member can be suspended and reinstated, and the editor's two step sign in reset", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members?q=samuel");
    await page.getByRole("button", { name: "Suspend samuel@demo.test" }).click();
    await page.getByLabel("Reason").fill("Checking the console");
    await page.getByRole("button", { name: "Suspend", exact: true }).click();
    await expect(page.getByText("Member suspended")).toBeVisible();
    await page.getByRole("button", { name: "Reinstate samuel@demo.test" }).click();
    await page.getByRole("button", { name: "Reinstate", exact: true }).click();
    await expect(page.getByText("Member reinstated")).toBeVisible();

    await page.goto("/admin/members?q=editor");
    await page.getByRole("button", { name: `Reset two step sign in for ${EDITOR}` }).click();
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText("Two step sign in reset")).toBeVisible();
  });

  test("invitations can be sent and withdrawn", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/invitations");
    const email = `invitee${Date.now()}@demo.test`;
    await page.getByLabel("Email address").fill(email);
    await page.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText(`Invitation sent to ${email}`)).toBeVisible();
    await page.getByRole("button", { name: `Withdraw the invitation to ${email}` }).click();
    await page.getByRole("button", { name: "Withdraw", exact: true }).click();
    await expect(page.getByText("Invitation withdrawn")).toBeVisible();
  });

  test("a waiting job is published", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/jobs");
    await page.getByRole("button", { name: "Publish" }).first().click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Job published")).toBeVisible();
  });

  test("a report is acted on and a win is published", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/reports");
    await page.getByRole("button", { name: "Hide the content" }).first().click();
    await page.getByLabel("Reason").fill("Spam");
    await page.getByRole("button", { name: "Hide", exact: true }).click();
    await expect(page.getByText("Content hidden")).toBeVisible();
    await page.goto("/admin/wins");
    await page.getByRole("button", { name: "Publish" }).first().click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Win published")).toBeVisible();
  });

  test("the code generator matches the published test vector", async () => {
    // RFC 6238: key "12345678901234567890" at 59 seconds gives 94287082, so 287082 with six digits.
    expect(totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59_000)).toBe("287082");
  });
});
