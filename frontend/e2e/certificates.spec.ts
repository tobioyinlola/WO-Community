import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const COURSE = "Fundraising for African startups";
const NUMBER = /WO-C-\d{4}-\d{6}/;
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

/** The number of the seeded certificate, read from the member's own list. */
async function numberOf(page: Page): Promise<string> {
  await page.goto("/app/learn/certificates");
  const card = page.getByRole("listitem").filter({ hasText: COURSE });
  await expect(card).toBeVisible();
  const text = (await card.textContent()) ?? "";
  return text.match(NUMBER)?.[0] ?? "";
}

async function publicPage(browser: Browser, baseURL: string | undefined) {
  const context = await browser.newContext({ baseURL });
  return { page: await context.newPage(), close: () => context.close() };
}

test.describe("certificates", () => {
  test("a member lists, views, downloads and shares a certificate", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.addInitScript(() => Object.defineProperty(navigator, "share", { value: undefined }));
    // Storage is a stand-in in this environment, so answer the signed link ourselves.
    await page.route("https://private.test/**", (route) =>
      route.fulfill({ status: 200, body: PDF, headers: { "content-type": "application/pdf", "content-disposition": 'attachment; filename="certificate.pdf"' } }),
    );
    await signIn(page);
    const number = await numberOf(page);
    expect(number).toMatch(NUMBER);

    await page.getByRole("link", { name: "View" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: COURSE })).toBeVisible();
    const sheet = page.getByRole("figure");
    await expect(sheet).toContainText("This certifies that");
    await expect(sheet).toContainText("has successfully completed");
    await expect(sheet).toContainText(number);
    // The sheet carries no QR code or web address; the number is checked on the verify page.
    await expect(sheet.getByRole("img", { name: /QR code/ })).toHaveCount(0);

    const downloading = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download certificate" }).click();
    expect((await downloading).suggestedFilename()).toBe("certificate.pdf");

    await page.getByRole("button", { name: "Share" }).click();
    await expect(page.getByText("Verification link copied")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(`/verify/${number}`);

    const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(result.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
  });

  test("a certificate is listed on the profile only when the holder turns it on", async ({ page, browser }, info) => {
    await signIn(page);
    const number = await numberOf(page);
    await page.getByRole("link", { name: "View" }).first().click();
    const choice = page.getByRole("switch", { name: "Show on my profile" });
    await expect(choice).not.toBeChecked();

    const other = await publicPage(browser, info.project.use.baseURL);
    const look = async () => {
      await other.page.goto("/app/directory");
      await other.page.getByText("Members", { exact: true }).click();
      await other.page.getByPlaceholder("A name, a company, a skill").fill("Amaka");
      await other.page.getByRole("button", { name: "Search", exact: true }).click();
      await other.page.getByRole("link", { name: /Amaka Obi/ }).first().click();
      await expect(other.page.getByRole("heading", { level: 1, name: "Amaka Obi" })).toBeVisible();
    };
    try {
      await signIn(other.page, "tunde@demo.test");
      await look();
      await expect(other.page.getByRole("heading", { name: "Certificates" })).toHaveCount(0);

      await choice.click();
      await expect(choice).toBeChecked();
      await expect(page.getByText("Shown on your profile")).toBeVisible();
      await look();
      const section = other.page.locator("aside").filter({ has: other.page.getByRole("heading", { name: "Certificates" }) });
      await expect(section).toContainText(COURSE);
      await expect(section.getByRole("link", { name: `Verify ${number}` })).toBeVisible();
      const result = await new AxeBuilder({ page: other.page }).withTags(TAGS).analyze();
      expect(result.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

      await choice.click();
      await expect(choice).not.toBeChecked();
      await expect(page.getByText("Hidden from your profile")).toBeVisible();
      await look();
      await expect(other.page.getByRole("heading", { name: "Certificates" })).toHaveCount(0);
    } finally {
      await other.close();
    }
  });

  test("anyone can verify a certificate, and an unknown number says so", async ({ page, browser }, info) => {
    await signIn(page);
    const number = await numberOf(page);
    const visitor = await publicPage(browser, info.project.use.baseURL);
    try {
      await visitor.page.goto(`/verify/${number}`);
      await expect(visitor.page.getByRole("heading", { level: 1, name: "Verify a certificate" })).toBeVisible();
      const card = visitor.page.locator('[data-state="valid"]');
      await expect(card).toContainText("Valid");
      await expect(card).toContainText(COURSE);
      await expect(card).not.toContainText("@");
      const result = await new AxeBuilder({ page: visitor.page }).withTags(TAGS).analyze();
      expect(result.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

      await visitor.page.goto("/verify/WO-C-2026-999999");
      await expect(visitor.page.locator('[data-state="unknown"]')).toContainText("Not found");
    } finally {
      await visitor.close();
    }
  });

  test("an admin edits the template with a live preview, then revokes and restores a certificate", async ({ page, browser }, info) => {
    await signInAdmin(page);
    await page.goto("/admin/learning/certificate-template");
    await expect(page.getByRole("heading", { level: 1, name: "Certificate template" })).toBeVisible();
    const sheet = page.getByRole("figure");
    const name = `Signatory ${Date.now() % 100000}`;
    await page.getByLabel("Signatory name").fill(name);
    await page.getByLabel("Title shown on the certificate").fill("Certificate of achievement");
    await expect(sheet).toContainText(name);
    await expect(sheet).toContainText("Certificate of achievement");
    await page.getByRole("button", { name: "Save template" }).click();
    await expect(page.getByText(/Template saved/)).toBeVisible();
    // Put the title back so other runs and screenshots see the default wording.
    await page.getByLabel("Title shown on the certificate").fill("Certificate of completion");
    await page.getByLabel("Signatory name").fill("Onyeka Obi");
    await page.getByRole("button", { name: "Save template" }).click();
    await expect(page.getByText(/Template saved/).first()).toBeVisible();
    await page.waitForTimeout(600); // let the notice finish fading in before the contrast check
    const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(result.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

    await page.goto("/admin/certificates");
    await expect(page.getByRole("heading", { level: 1, name: "Certificates" })).toBeVisible();
    await page.getByLabel("Search certificates").fill("Fundraising");
    const row = page.getByRole("row").filter({ hasText: COURSE }).first();
    await expect(row).toBeVisible();
    const number = ((await row.textContent()) ?? "").match(NUMBER)?.[0] ?? "";
    await row.getByRole("button", { name: `Revoke certificate ${number}` }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Revoke certificate" })).toBeDisabled();
    await dialog.getByLabel("Reason").fill("Issued in error (browser test)");
    await dialog.getByRole("button", { name: "Revoke certificate" }).click();
    await expect(page.getByText("Certificate revoked")).toBeVisible();

    const visitor = await publicPage(browser, info.project.use.baseURL);
    try {
      await visitor.page.goto(`/verify/${number}`);
      await expect(visitor.page.locator('[data-state="revoked"]')).toContainText("Revoked");
      await expect(visitor.page.locator('[data-state="revoked"]')).not.toContainText(COURSE);
    } finally {
      await visitor.close();
    }

    await page.getByRole("button", { name: `Restore certificate ${number}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Restore certificate" }).click();
    await expect(page.getByText("Certificate restored")).toBeVisible();
    const again = await publicPage(browser, info.project.use.baseURL);
    try {
      await again.page.goto(`/verify/${number}`);
      await expect(again.page.locator('[data-state="valid"]')).toContainText("Valid");
    } finally {
      await again.close();
    }
  });
});
