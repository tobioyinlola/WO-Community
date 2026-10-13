import { expect, test } from "@playwright/test";
import { MEMBER, signIn, signInAdmin } from "./helpers";

/**
 * Drives the built front end against the API running with the production settings (see
 * docs/deployment/local-production-run.md). It only runs when E2E_PRODUCTION_RUN is set, with
 * E2E_BASE_URL at the built front end and MAIL_CATCHER_URL at the mail catcher's address.
 */
test.skip(!process.env.E2E_PRODUCTION_RUN, "needs the production style stack");
test.describe.configure({ mode: "serial" });

const API = process.env.E2E_API_URL ?? "http://localhost:8001";
const MAIL = process.env.MAIL_CATCHER_URL ?? "http://localhost:8026";

// A real 1x1 PNG.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test("sign in works across the app and API hosts, and the cookie is set by the API", async ({ page }) => {
  await signIn(page);
  const cookies = await page.context().cookies(`${API}/api/v1/auth/refresh`);
  const refresh = cookies.find((c) => c.name === "wo_refresh");
  expect(refresh, "the refresh cookie").toBeTruthy();
  expect(refresh?.httpOnly).toBe(true);
  expect(refresh?.secure).toBe(true);
  expect(refresh?.sameSite).toBe("Lax");
});

test("a course page opens", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/learn");
  await page.locator("a[href*='/app/learn/courses/']").first().click();
  await expect(page).toHaveURL(/\/app\/learn\/courses\//);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("an image is uploaded through a signed PUT, checked, and served from the media address", async ({ page }) => {
  await signInAdmin(page);
  await page.goto("/admin/courses");
  await page.locator("a[href*='/admin/courses/']").first().click();
  await page.getByRole("tab", { name: /Settings/ }).click();
  await page.locator("#settings-cover").setInputFiles({ name: "cover.png", mimeType: "image/png", buffer: PNG });
  const upload = page.waitForResponse((r) => r.request().method() === "PUT" && r.url().includes("/wo-quarantine/"));
  const cover = page.waitForResponse((r) => r.request().method() === "PUT" && r.url().endsWith("/cover"), { timeout: 60_000 });
  await page.getByRole("button", { name: "Save changes" }).click();
  expect((await upload).ok()).toBe(true);
  // The worker scans the file and rebuilds the image before the cover can be attached.
  expect((await cover).ok()).toBe(true);
  // The public image is rebuilt and published under the media address.
  await page.goto("/app/learn");
  const image = page.locator("img[src*='wo-media']").first();
  await expect(image).toBeVisible();
  const status = await page.evaluate(async (src) => (await fetch(src)).status, await image.getAttribute("src"));
  expect(status).toBe(200);
});

test("a password reset email arrives in the mail catcher with a link to the app", async ({ page, request }) => {
  await request.delete(`${MAIL}/api/v1/messages`);
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(MEMBER);
  await page.getByRole("button", { name: /Send|Email|Reset/ }).first().click();
  await expect(page.getByRole("status").or(page.getByText(/check your email|if an account/i)).first()).toBeVisible();
  let message: { ID: string; Subject: string } | undefined;
  await expect
    .poll(
      async () => {
        const list = await (await request.get(`${MAIL}/api/v1/messages`)).json();
        message = list.messages?.[0];
        return Boolean(message);
      },
      { timeout: 30_000, message: "the worker should send the reset email" },
    )
    .toBe(true);
  const full = await (await request.get(`${MAIL}/api/v1/message/${message!.ID}`)).json();
  expect(full.To[0].Address).toBe(MEMBER);
  expect(full.Text).toContain("http://localhost:4173/");
  expect(full.HTML).toContain("The WO Community Team");
  expect(full.Text).toContain("Best regards");
});
