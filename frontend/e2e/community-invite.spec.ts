import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

const LINK = "https://chat.whatsapp.com/test-invite";

/** Answers /me as a member who is still due the invitation, and records what the page reports back. */
async function dueInvitation(page: Page) {
  const calls: string[] = [];
  await page.route("**/api/v1/me", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), community_invite_url: LINK } });
  });
  await page.route("**/api/v1/me/community-invite/*", async (route) => {
    calls.push(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    await route.fulfill({ status: 204 });
  });
  return calls;
}

test("a member is invited to the WhatsApp community once per sign-in", async ({ page }) => {
  const calls = await dueInvitation(page);
  await signIn(page, undefined, { invite: true });
  const dialog = page.getByRole("dialog", { name: "Join our WhatsApp community" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Join on WhatsApp" })).toHaveAttribute("href", LINK);
  await dialog.getByRole("button", { name: "Maybe later" }).click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Join our WhatsApp community" })).toHaveCount(0);
  expect(calls).toEqual(["shown"]);
});

test("following the link tells the server the member joined", async ({ page, context }) => {
  const calls = await dueInvitation(page);
  await signIn(page, undefined, { invite: true });
  const popup = context.waitForEvent("page");
  await page.getByRole("link", { name: "Join on WhatsApp" }).click();
  await (await popup).close();
  await expect.poll(() => calls).toContain("joined");
  await expect(page.getByRole("dialog", { name: "Join our WhatsApp community" })).toHaveCount(0);
});
