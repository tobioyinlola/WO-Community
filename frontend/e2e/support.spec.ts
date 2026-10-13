import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const SUBJECT = `Cannot update my startup ${Date.now() % 100000}`;
const MESSAGE = "I tried to change my startup description yesterday and the page keeps showing the old text.";

test.describe("support", () => {
  test("a member sends a request from the drawer and finds it in their list", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Contact support" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Contact support" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText(/Sending as/)).toBeVisible();

    // Nothing is sent until it is valid.
    await drawer.getByLabel("Subject").fill("Hi");
    await drawer.getByLabel("Message").fill("Too short");
    await drawer.getByRole("button", { name: "Send request" }).click();
    await expect(drawer.getByText(/at least/).first()).toBeVisible();

    await drawer.getByLabel("Category").selectOption("profile");
    await drawer.getByLabel("Subject").fill(SUBJECT);
    await drawer.getByLabel("Message").fill(MESSAGE);
    await drawer.getByRole("button", { name: "Send request" }).click();
    await expect(drawer.getByText("We have your request")).toBeVisible();
    await expect(drawer.getByText(/SUP-\d+/)).toBeVisible();
    await drawer.getByRole("link", { name: "View request" }).click();
    await expect(page.getByRole("heading", { level: 1, name: SUBJECT })).toBeVisible();
    await expect(page.getByText("Open", { exact: true }).first()).toBeVisible();

    await page.goto("/app/support");
    const row = page.getByRole("link", { name: new RegExp(SUBJECT) });
    await expect(row).toBeVisible();
    await expect(row.getByText("Open", { exact: true })).toBeVisible();
  });

  test("closing the drawer asks first when something was typed", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Contact support" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Contact support" });
    await drawer.getByLabel("Subject").fill("Half written");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("alertdialog", { name: "Discard your changes?" })).toBeVisible();
    await page.getByRole("button", { name: "Keep editing" }).click();
    await expect(drawer.getByLabel("Subject")).toHaveValue("Half written");
    await page.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Discard" }).click();
    await expect(drawer).toBeHidden();
  });

  test("an admin answers, the member replies, the admin resolves and the member sees it", async ({ page, browser }) => {
    const admin = await browser.newContext({ timezoneId: "Africa/Lagos" });
    const adminPage = await admin.newPage();
    await signInAdmin(adminPage);

    // The admin finds the request in the inbox and answers it.
    await adminPage.goto("/admin/support");
    await expect(adminPage.getByRole("heading", { level: 1, name: "Support inbox" })).toBeVisible();
    await adminPage.getByRole("button", { name: new RegExp(SUBJECT) }).or(adminPage.getByText(SUBJECT)).first().click();
    const ticket = adminPage.getByRole("dialog", { name: SUBJECT });
    await expect(ticket).toBeVisible();
    await expect(ticket.getByText("Amaka Obi").first()).toBeVisible();
    await ticket.getByRole("textbox", { name: "Reply" }).fill("Thanks for flagging this. Which page were you editing?");
    await ticket.getByRole("button", { name: "Send reply" }).click();
    await expect(adminPage.getByText("Reply sent")).toBeVisible();

    // The member sees the answer and that it is waiting on them.
    await signIn(page);
    await page.goto("/app/support");
    await page.getByRole("link", { name: new RegExp(SUBJECT) }).click();
    await expect(page.getByText("Support is waiting for your reply")).toBeVisible();
    await expect(page.getByText("Which page were you editing?")).toBeVisible();
    await page.getByLabel("Your reply").fill("The startup page, under About.");
    await page.getByRole("button", { name: "Send reply" }).click();
    await expect(page.getByText("The startup page, under About.")).toBeVisible();
    await expect(page.getByText("Support is waiting for your reply")).toBeHidden();

    // An internal note stays with the admins.
    await adminPage.goto("/admin/support");
    await adminPage.getByText(SUBJECT).first().click();
    const again = adminPage.getByRole("dialog", { name: SUBJECT });
    await expect(again.getByText("The startup page, under About.")).toBeVisible();
    await again.getByRole("switch", { name: /Internal note/ }).check();
    await again.getByRole("textbox", { name: "Internal note" }).fill("Probably the cached page. Resolve if it clears.");
    await again.getByRole("button", { name: "Add note" }).click();
    await expect(adminPage.getByText("Note added")).toBeVisible();
    await expect(again.getByText("Internal note", { exact: true }).first()).toBeVisible();

    // Resolve it.
    await again.getByRole("switch", { name: /Internal note/ }).uncheck();
    await again.getByRole("button", { name: "Resolve", exact: true }).click();
    await expect(adminPage.getByText("Request resolved")).toBeVisible();
    await admin.close();

    await page.reload();
    await expect(page.getByText("This request is resolved")).toBeVisible();
    await expect(page.getByText("Was this helpful?")).toBeVisible();
    await expect(page.getByText("Probably the cached page")).toHaveCount(0);
    await page.getByRole("button", { name: "Yes" }).click();
    await expect(page.getByText(/glad it helped/)).toBeVisible();
    await page.getByRole("button", { name: "Reopen" }).click();
    await expect(page.getByLabel("Your reply")).toBeVisible();
  });

  test("someone who cannot sign in can ask for help, and the sign in page points there", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Contact support" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Trouble signing in?" })).toBeVisible();
    await page.getByLabel("Your name").fill("Kemi Adeyemi");
    await page.getByLabel("Email we can reach you on").fill("kemi@example.com");
    await page.getByLabel("Subject").fill("Cannot sign in on my phone");
    await page.getByLabel("What is happening?").fill("The page says my password is wrong but I reset it earlier today.");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText("We have your message")).toBeVisible();
    await expect(page.getByRole("link", { name: "Back to sign in" })).toBeVisible();
  });

  test("the open drawers pass the accessibility checks", async ({ page, browser }) => {
    const rules = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
    await signIn(page);
    await page.getByRole("button", { name: "Contact support" }).first().click();
    const member = page.getByRole("dialog", { name: "Contact support" });
    await expect(member).toBeVisible();
    const mine = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(rules).analyze();
    expect(mine.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

    const admin = await browser.newContext({ timezoneId: "Africa/Lagos" });
    const adminPage = await admin.newPage();
    await signInAdmin(adminPage);
    await adminPage.goto("/admin/support?tab=all");
    await adminPage.getByText(SUBJECT).first().click();
    await expect(adminPage.getByRole("dialog", { name: SUBJECT })).toBeVisible();
    const theirs = await new AxeBuilder({ page: adminPage }).include('[role="dialog"]').withTags(rules).analyze();
    expect(theirs.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
    await admin.close();
  });
});
