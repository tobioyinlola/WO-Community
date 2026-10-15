import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const STAMP = Date.now() % 1_000_000;
const APPLICANT = `Referred Applicant ${STAMP}`;
const EMAIL = `referred.${STAMP}@demo.test`;

/** Fills the four steps up to the last one, where the referral question is. */
async function reachLastStep(page: Page) {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill("a-long-passphrase-2026");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Full name").fill(APPLICANT);
  await page.getByLabel("Country").selectOption({ label: "Nigeria" });
  await page.getByLabel("City").fill("Lagos");
  await page.getByLabel("LinkedIn profile").fill("linkedin.com/in/new-member");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Company name").fill(`Referral Labs ${STAMP}`);
  await page.getByLabel("Company website").fill("newcompany.example.com");
  await page.getByLabel("Sector").selectOption({ label: "Fintech" });
  await page.getByLabel("Stage").selectOption({ index: 1 });
  await page.getByLabel("What does it do?").fill("Payments for small shops.");
  await page.getByRole("button", { name: "Continue" }).click();
}

async function agree(page: Page) {
  await page.getByLabel(/I accept the\s+terms/).check();
  await page.getByLabel(/privacy policy/).check();
  await page.getByLabel(/code of conduct/).check();
}

test.describe("referrals", () => {
  test("a newcomer finds the member who told them and names them", async ({ page }) => {
    await page.goto("/register");
    await reachLastStep(page);
    const group = page.getByRole("group", { name: "Who referred you?" });
    await expect(group.getByText("Optional")).toBeVisible();
    await group.getByLabel("How did you hear about us?").selectOption({ label: "A WO Community member" });
    await group.getByLabel("Search for them").fill("Amaka");
    await group.getByRole("button", { name: /Amaka Obi/ }).click();
    await expect(group.getByRole("group", { name: "The member who referred you" })).toContainText("Amaka Obi");
    await agree(page);
    await page.getByRole("button", { name: "Request access" }).click();
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  });

  test("the admin sees who referred them in the table and the drawer, and can correct it", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/approvals?tab=unconfirmed");
    const row = page.getByRole("row").filter({ hasText: EMAIL });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Amaka Obi");
    await row.click();
    const drawer = page.getByRole("dialog", { name: EMAIL });
    await expect(drawer.getByText("Referred by")).toBeVisible();
    await expect(drawer.getByText(/A WO Community member: Amaka Obi/)).toBeVisible();

    await drawer.getByRole("button", { name: "Edit" }).click();
    const editor = page.getByRole("dialog", { name: "How they heard of us" });
    await editor.getByLabel("Source").selectOption({ label: "An event or demo day" });
    await editor.getByLabel("Detail").fill("Demo Day, Lagos");
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Referral updated")).toBeVisible();
    await expect(drawer.getByText("An event or demo day: Demo Day, Lagos")).toBeVisible();

    // And back again, so the next run starts the same.
    await drawer.getByRole("button", { name: "Edit" }).click();
    await editor.getByLabel("Source").selectOption({ label: "A WO Community member" });
    await editor.getByLabel("Find the member").fill("amaka");
    await editor.getByRole("button", { name: /Amaka Obi/ }).first().click();
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(drawer.getByText(/A WO Community member: Amaka Obi/)).toBeVisible();
  });

  test("the members table can be filtered by how people heard of us", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members");
    await page.getByLabel("How they heard of us").selectOption({ label: "A WO Community member" });
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page.getByRole("button", { name: /Remove filter Source: A WO Community member/ })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(EMAIL) })).toBeVisible();
  });

  test("the dashboard shows referrals, where people heard of us, and top referrers", async ({ page }) => {
    await signInAdmin(page);
    await expect(page.getByRole("region", { name: "Referrals" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Where people heard of us" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Top referrers" })).toBeVisible();
    await expect(page.getByRole("list").filter({ hasText: "A WO Community member" }).first()).toBeVisible();
  });

  test("a member shares a link that opens sign up with them chosen", async ({ page, browser }) => {
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await signIn(page);
    const card = page.getByRole("region", { name: "Your referrals" }).or(page.locator("section").filter({ hasText: "Your referrals" })).first();
    const link = (await card.getByLabel("Your referral link").textContent())?.trim() ?? "";
    expect(link).toMatch(/\/join\?ref=[A-Z2-9]{8}$/);
    await card.getByRole("button", { name: "Copy link" }).click();
    await expect(page.getByText("Link copied")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);

    const visitor = await browser.newContext();
    const fresh = await visitor.newPage();
    await fresh.goto(link.replace(/^https?:\/\/[^/]+/, ""));
    await expect(fresh).toHaveURL(/\/register\?ref=/);
    await fresh.getByLabel("Email").fill(`link.${STAMP}@demo.test`);
    await fresh.getByLabel("Password", { exact: true }).fill("a-long-passphrase-2026");
    await fresh.getByRole("button", { name: "Continue" }).click();
    await fresh.getByLabel("Full name").fill(`Link Applicant ${STAMP}`);
    await fresh.getByLabel("Country").selectOption({ label: "Nigeria" });
    await fresh.getByLabel("City").fill("Lagos");
    await fresh.getByLabel("LinkedIn profile").fill("linkedin.com/in/new-member");
    await fresh.getByRole("button", { name: "Continue" }).click();
    await fresh.getByLabel("Company name").fill(`Link Labs ${STAMP}`);
    await fresh.getByLabel("Company website").fill("newcompany.example.com");
    await fresh.getByLabel("Sector").selectOption({ label: "Fintech" });
    await fresh.getByLabel("Stage").selectOption({ index: 1 });
    await fresh.getByLabel("What does it do?").fill("Logistics for traders.");
    await fresh.getByRole("button", { name: "Continue" }).click();
    const group = fresh.getByRole("group", { name: "Who referred you?" });
    await expect(group.getByText(/joining through .* link/)).toBeVisible();
    await expect(group.getByLabel("How did you hear about us?")).toHaveValue("member");
    await agree(fresh);
    await fresh.getByRole("button", { name: "Request access" }).click();
    await expect(fresh.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await visitor.close();
  });

  test("the referral question passes the accessibility checks, with the search open", async ({ page }) => {
    await page.goto("/register");
    await reachLastStep(page);
    const group = page.getByRole("group", { name: "Who referred you?" });
    await group.getByLabel("How did you hear about us?").selectOption({ label: "A WO Community member" });
    await group.getByLabel("Search for them").fill("Amaka");
    await expect(group.getByRole("button", { name: /Amaka Obi/ })).toBeVisible();
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    expect(result.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
  });
});
