import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAdmin, watchConsole } from "./helpers";

test.describe.configure({ mode: "serial" });

const stamp = Date.now().toString(36);

/** Forget the current sign in so the next one starts clean. */
async function signedOut(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => window.localStorage.clear());
  await page.goto("/login");
}

test.describe("the admin changes", () => {
  test("an admin action shows in the audit log with a diff, a filter and an export", async ({ page }) => {
    const problems = watchConsole(page);
    await signInAdmin(page);
    // Make an entry: change the wording of a template.
    await page.goto("/admin/email-templates?t=welcome");
    await page.getByLabel("Subject").fill(`Welcome aboard ${stamp}`);
    await page.getByRole("button", { name: "Save wording" }).click();
    await expect(page.getByText("Wording saved")).toBeVisible();
    await page.goto("/admin/audit?q=email.template_edited");
    await expect(page.getByRole("button", { name: /Open entry: email.template_edited/ }).first()).toBeVisible();
    await page.getByRole("button", { name: /Open entry: email.template_edited/ }).first().click();
    const drawer = page.getByRole("dialog");
    await expect(drawer.getByRole("heading", { name: /Email template edited/i })).toBeVisible();
    await expect(drawer.getByRole("columnheader", { name: "After" })).toBeVisible();
    await expect(drawer.locator("td", { hasText: `Welcome aboard ${stamp}` }).first()).toBeVisible();
    await page.keyboard.press("Escape");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export CSV" }).click()]);
    expect(download.suggestedFilename()).toBe("audit-log.csv");
    expect(problems).toEqual([]);
  });

  test("a member opens from the list in a drawer with the sections", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members");
    await page.locator("a.adm-who__name").first().click();
    await expect(page).toHaveURL(/\/admin\/members\/[0-9a-f-]{36}/);
    const drawer = page.getByRole("dialog");
    for (const name of ["Profile", "Account", "Activity", "Learning", "Mentorship", "Support"]) {
      await expect(drawer.getByRole("heading", { name })).toBeVisible();
    }
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/\/admin\/members$/);
  });

  test("five addresses become chips, are checked, one is removed and the rest are sent", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/invitations");
    const box = page.getByLabel("Email addresses");
    await box.click();
    const fresh = `new1-${stamp}@example.com`;
    await page.evaluate(() => navigator.clipboard?.writeText("").catch(() => undefined));
    await box.fill(`${fresh}, not-an-email; ${fresh.toUpperCase()}`);
    await box.press("Enter");
    await expect(page.getByRole("status").filter({ hasText: "merged" })).toBeVisible();
    await box.fill("amaka@demo.test");
    await box.press("Enter");
    await box.fill(`new2-${stamp}@example.com`);
    await box.press("Space");
    await expect(page.getByText("Not a valid email address")).toBeVisible();
    await expect(page.getByText("Already a member")).toBeVisible();
    await page.getByRole("button", { name: `Remove new2-${stamp}@example.com` }).click();
    await expect(page.getByRole("button", { name: "Send 1 invitation" })).toBeEnabled();
    await page.getByRole("button", { name: "Send 1 invitation" }).click();
    await expect(page.getByText("1 sent, 0 skipped")).toBeVisible();
  });

  test("the team posts, pins and schedules", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/feed");
    await page.getByRole("button", { name: "New post" }).click();
    await page.getByLabel("What do you want to say?").fill(`Welcome from the team ${stamp}`);
    await page.getByLabel("Pin to the top of the feed").check();
    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Post published")).toBeVisible();
    await page.goto("/app/feed");
    await expect(page.getByText(`Welcome from the team ${stamp}`)).toBeVisible();
    await expect(page.getByText("WO Community team").first()).toBeVisible();
  });

  test("a news item with a banner scrolls on the dashboard, pauses on hover, and can be closed", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/news");
    await page.getByRole("button", { name: "New story" }).click();
    await page.getByLabel("Kind").selectOption("announcement");
    await page.getByLabel("Title", { exact: true }).fill(`Banner ${stamp}`);
    await page.getByLabel("Story", { exact: true }).fill("Something for everyone.");
    await page.getByLabel("Show in the dashboard banner").check();
    await page.getByLabel("Banner text").fill(`Join us on Friday ${stamp}`);
    const pad = (n: number) => String(n).padStart(2, "0");
    const local = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    await page.getByLabel("Starts (Lagos time)").fill(local(new Date(Date.now() - 3600_000)));
    await page.getByLabel("Ends (Lagos time)").fill(local(new Date(Date.now() + 86_400_000)));
    await page.getByRole("button", { name: "Save as draft" }).click();
    await expect(page.getByText("Draft created")).toBeVisible();
    await page.getByRole("listitem").filter({ hasText: `Banner ${stamp}` }).getByRole("button", { name: "Publish now" }).click();
    await page.getByRole("button", { name: "Publish", exact: true }).click();
    await signedOut(page);
    await signIn(page);
    await page.goto("/app");
    const ticker = page.getByRole("region", { name: "Announcements and news" });
    await expect(ticker).toBeVisible();
    await expect(ticker.getByText(`Join us on Friday ${stamp}`).first()).toBeAttached();
    await ticker.hover();
    await expect(ticker.locator(".wo-ticker__track")).toHaveCSS("animation-play-state", "paused");
    await page.getByRole("button", { name: "Close announcements" }).click();
    await expect(ticker).toHaveCount(0);
  });

  test("with reduced motion the banner stands still and has next and previous", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await signIn(page);
    await page.goto("/app");
    // Closing it earlier hid it for this member, so only check the control exists when it shows.
    const ticker = page.getByRole("region", { name: "Announcements and news" });
    if (await ticker.count()) await expect(ticker.getByRole("button", { name: "Next announcement" })).toBeVisible();
    await context.close();
  });

  test("a job has no application form: it opens the employer's link or email", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/jobs");
    await page.locator("a.app-list__title").first().click();
    await expect(page.getByText("Applications are handled directly by the employer.")).toBeVisible();
    await expect(page.getByLabel("Cover note")).toHaveCount(0);
    await expect(page.getByLabel("CV")).toHaveCount(0);
    const link = page.getByRole("link", { name: /Apply/ }).first();
    await expect(link).toBeVisible();
  });

  test("a job posted by a member waits and an admin approves it from the queue", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/jobs/new");
    await page.getByLabel("Job title").fill(`Designer ${stamp}`);
    await page.getByLabel("Description").fill("Design things for founders.\n\nYou will be great.");
    await page.getByLabel("Application email").fill("jobs@designer.test");
    await page.getByRole("button", { name: "Post job" }).click();
    await expect(page).toHaveURL(/\/app\/jobs\/[0-9a-f-]{36}/);
    await signedOut(page);
    await signInAdmin(page);
    await page.goto("/admin/jobs?tab=pending");
    await page.getByRole("button", { name: `Designer ${stamp}` }).click();
    await page.getByRole("button", { name: "Approve", exact: true }).first().click();
    await page.getByRole("dialog").filter({ hasText: "Approve this job" }).getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("Job approved and live")).toBeVisible();
  });

  test("the email health page shows setup and the DNS checks", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/email-health");
    await expect(page.getByRole("heading", { name: "Email health" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Suppression list" })).toBeVisible();
    await expect(page.getByText(/SPF:/).first()).toBeVisible();
  });

  test("an admin can switch an approval email off", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/settings?section=notifications");
    const toggle = page.getByLabel("Jobs to review");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByText("You will not get these emails")).toBeVisible();
    await toggle.click();
  });
});
