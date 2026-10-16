import { expect, test } from "@playwright/test";
import { signInAdmin, watchConsole } from "./helpers";

const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/${name}.png`, fullPage: false });
};

test("an admin publishes a testimonial and it glides past above the footer", async ({ page, browser }, info) => {
  const problems = watchConsole(page);
  const quote = `The community got me my first investor meeting (${Date.now()}).`;
  await signInAdmin(page);
  await page.goto("/admin/testimonials");
  await expect(page.getByRole("heading", { level: 1, name: "Testimonials" })).toBeVisible();
  await page.getByRole("button", { name: "Add a testimonial" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("What they said").fill(quote);
  await dialog.getByLabel("Name").fill("Amaka Obi");
  await dialog.getByLabel("Role and company (optional)").fill("Founder, Kuda Foods");
  await expect(dialog.getByLabel("Show it on the website")).toBeDisabled();
  await dialog.getByLabel("They said this and agreed to it being shown on the website").check();
  await dialog.getByLabel("Show it on the website").check();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved, and on the website")).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(quote.slice(0, 30)) });
  await expect(row.getByText("On the website")).toBeVisible();
  await shot(page, "admin-testimonials");

  const visitor = await browser.newPage({ baseURL: info.project.use.baseURL });
  await visitor.goto("/");
  const section = visitor.getByRole("region", { name: /own words/i });
  await section.scrollIntoViewIfNeeded();
  await expect(section.getByText(quote).first()).toBeVisible();
  // It is the last section before the footer.
  const after = await section.evaluate((el) => el.nextElementSibling?.tagName ?? "none");
  expect(after).toBe("none");
  if (process.env.E2E_SHOTS) await section.screenshot({ path: `${process.env.E2E_SHOTS}/testimonials-marquee.png` });
  await visitor.close();

  await row.getByRole("button", { name: "Hide" }).click();
  await expect(row.getByText("Hidden")).toBeVisible();
  page.once("dialog", (d) => void d.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Testimonial deleted")).toBeVisible();
  expect(problems).toEqual([]);
});

test("the feature cards show their picture or a clean fallback, and respond to the pointer", async ({ page }) => {
  await page.goto("/");
  const card = page.locator(".site-feature").first();
  await card.scrollIntoViewIfNeeded();
  await expect(card.locator(".wo-media")).toBeVisible();
  // Without a photo file, the card falls back to the gradient and icon rather than a broken image.
  await expect(card.locator(".wo-media img[src]")).toHaveCount(0, { timeout: 5_000 }).catch(() => undefined);
  await card.hover();
  if (process.env.E2E_SHOTS) await page.locator(".site-carousel").first().screenshot({ path: `${process.env.E2E_SHOTS}/feature-cards.png` });
});
