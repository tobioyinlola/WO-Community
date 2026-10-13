import { expect, type Page } from "@playwright/test";
import { ADMIN_KEY, freshCode } from "./totp";

export const PASSWORD = "Demo-Passw0rd-2026";

export const MEMBER = "amaka@demo.test";
export const MENTOR = "ada@demo.test";
export const PENDING = "pending@demo.test";

/** Signs in through the real form and waits until the app has loaded. */
export async function signIn(page: Page, email = MEMBER): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app/);
}

/** Fails a test if the page logged an error to the console. */
export function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  // The brand logo files are supplied separately; until they are added the app falls back to text.
  page.on("response", (response) => {
    // A venture with no score, plan or forecast yet answers 404 by design; the screens show an empty state.
    const expectedMissing = response.status() === 404 && /\/toolkit\/ventures\/[^/]+\/(score\/latest|plan|forecast)$/.test(response.url());
    if (response.status() >= 400 && !expectedMissing && !response.url().includes("/assets/wo-")) {
      problems.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error" && !text.startsWith("Failed to load resource")) problems.push(text);
  });
  page.on("pageerror", (error) => problems.push(error.message));
  return problems;
}

/** Signs in as the demo admin: password, then the code from the authenticator. */
export async function signInAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.test");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Enter your code" })).toBeVisible();
  // Each code works once. A run that started less than 30 seconds after the last one reuses its
  // code and is refused, so wait for the next code and try again.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.getByLabel("Code").fill(await freshCode(ADMIN_KEY, attempt > 0));
    await page.getByRole("button", { name: "Confirm" }).click();
    const rejected = page.getByRole("alert");
    await expect(page).toHaveURL(/\/app/, { timeout: attempt === 0 ? 6_000 : 20_000 }).catch(async () => {
      if (attempt > 0 || (await rejected.count()) === 0) throw new Error("The code was not accepted");
    });
    if (/\/app/.test(page.url())) break;
  }
  await page.goto("/admin");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
}
