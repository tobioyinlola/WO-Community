import { expect, test } from "@playwright/test";
import { signIn, watchConsole } from "./helpers";

// A fake microphone (a steady tone) and audio that may play without a tap, so a test can talk.
test.use({
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
    ...(process.env.E2E_EXECUTABLE ? { executablePath: process.env.E2E_EXECUTABLE } : {}),
  },
  permissions: ["microphone"],
});

test("a member can talk to Onyeka and hear the answer", async ({ page }) => {
  const problems = watchConsole(page);
  await signIn(page);
  await page.getByRole("button", { name: "Ask Onyeka" }).click();
  const panel = page.getByRole("dialog", { name: "Onyeka" });
  const startOver = panel.getByRole("button", { name: "Start over" });
  if (await startOver.isVisible()) await startOver.click();

  await panel.getByRole("button", { name: "Talk to Onyeka" }).click();
  const bar = panel.getByRole("group", { name: "Voice conversation" });
  await expect(bar.getByText(/Listening/)).toBeVisible();
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/onyeka-voice-listening.png` });
  await page.waitForTimeout(1200);
  await bar.getByRole("button", { name: "Done" }).click();

  // The words appear as the member's message, Onyeka answers, reads it out, then listens again.
  await expect(panel.locator('.onyeka-msg[data-author="user"]')).toHaveCount(1, { timeout: 20_000 });
  await expect(panel.locator('.onyeka-msg[data-author="assistant"]')).toHaveCount(2, { timeout: 20_000 });
  await expect(bar.getByText(/Listening/)).toBeVisible({ timeout: 20_000 });
  await bar.getByRole("button", { name: "End voice conversation" }).click();
  await expect(bar).toHaveCount(0);
  await expect(panel.getByLabel("Message Onyeka")).toBeVisible();

  // Any answer can be heard again on its own.
  const listen = panel.getByRole("button", { name: "Listen" }).first();
  await listen.click();
  await expect(panel.getByRole("button", { name: "Listen" }).first()).toBeVisible({ timeout: 10_000 });
  await startOver.click();
  expect(problems).toEqual([]);
});
