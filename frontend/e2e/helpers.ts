import { expect, type Page } from "@playwright/test";

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
    if (response.status() >= 400 && !response.url().includes("/assets/wo-")) {
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
