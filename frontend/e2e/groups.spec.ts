import { expect, test } from "@playwright/test";
import { MENTOR, signIn, signInAdmin, watchConsole } from "./helpers";

const SHOTS = process.env.E2E_SHOTS ?? "";

test.describe("groups", () => {
  test("members join a group, chat with emoji, react and reply", async ({ browser }) => {
    const amaka = await browser.newPage();
    const problems = watchConsole(amaka);
    await signIn(amaka);
    await amaka.getByRole("link", { name: "Groups", exact: true }).first().click();
    await expect(amaka.getByRole("heading", { level: 1, name: "Groups" })).toBeVisible();
    await amaka.getByRole("navigation", { name: "Groups" }).getByRole("link", { name: /WO Sport Group/ }).click();

    const joinButton = amaka.getByRole("button", { name: "Join group" });
    if (await joinButton.isVisible()) await joinButton.click();
    const box = amaka.getByLabel("Message WO Sport Group");
    await expect(box).toBeVisible();

    const words = `Five-a-side on Saturday ${Date.now()}`;
    await box.fill(`${words} `);
    await amaka.getByRole("button", { name: "Add an emoji" }).click();
    await amaka.getByRole("dialog", { name: "Choose an emoji" }).getByRole("tab", { name: "Sport" }).click();
    await amaka.getByRole("dialog", { name: "Choose an emoji" }).getByRole("button", { name: "⚽" }).click();
    await amaka.keyboard.press("Escape");
    await box.press("Enter");
    const mine = amaka.locator(".wo-msg").filter({ hasText: words });
    await expect(mine).toContainText("⚽");

    // A second member sees it, reacts and replies.
    const ada = await browser.newPage();
    await signIn(ada, MENTOR);
    await ada.goto("/app/groups");
    await ada.getByRole("navigation", { name: "Groups" }).getByRole("link", { name: /WO Sport Group/ }).click();
    const join = ada.getByRole("button", { name: "Join group" });
    if (await join.isVisible()) await join.click();
    const theirs = ada.locator(".wo-msg").filter({ hasText: words });
    await expect(theirs).toBeVisible();
    await theirs.hover();
    await theirs.getByRole("button", { name: "React with 🔥" }).click();
    await expect(theirs.getByRole("button", { name: /🔥 1, including you/ })).toBeVisible();
    await theirs.getByRole("button", { name: "Reply" }).click();
    await ada.getByLabel("Message WO Sport Group").fill("Count me in 🙌🏾");
    await ada.getByRole("button", { name: "Send" }).click();
    const reply = ada.locator(".wo-msg").filter({ hasText: "Count me in" }).last();
    await expect(reply.locator(".wo-msg__quote")).toContainText("Five-a-side");

    // Back in Amaka's window the reaction and the reply arrive without reloading.
    await expect(mine.getByRole("button", { name: /🔥 1/ })).toBeVisible({ timeout: 10_000 });
    await expect(amaka.locator(".wo-msg").filter({ hasText: "Count me in" }).last()).toBeVisible({ timeout: 10_000 });
    if (SHOTS) await amaka.screenshot({ path: `${SHOTS}/groups-chat.png` });
    expect(problems).toEqual([]);
    await ada.close();
    await amaka.close();
  });

  test("an admin opens a new group and members find it", async ({ browser }) => {
    const admin = await browser.newPage();
    await signInAdmin(admin);
    await admin.goto("/admin/groups");
    await expect(admin.getByRole("heading", { level: 1, name: "Groups" })).toBeVisible();
    const name = `WO Book Club ${Date.now() % 100000}`;
    await admin.getByRole("button", { name: "New group" }).click();
    const form = admin.getByRole("dialog", { name: "New group" });
    await form.getByLabel("Name", { exact: true }).fill(name);
    await form.getByLabel("Emoji", { exact: true }).fill("📚");
    await form.getByLabel("Description").fill("What we are reading this month.");
    await form.getByRole("button", { name: "Create group" }).click();
    await expect(admin.getByText(`${name} is open for members to join`).first()).toBeVisible();
    if (SHOTS) await admin.screenshot({ path: `${SHOTS}/groups-admin.png` });

    const member = await browser.newPage();
    await signIn(member);
    await member.goto("/app/groups");
    await expect(member.getByRole("navigation", { name: "Groups" }).getByRole("link", { name: new RegExp(name) })).toBeVisible();

    // Archived, it is gone for members.
    await admin.locator(".adm-group").filter({ hasText: name }).getByRole("button", { name: "Archive" }).click();
    await expect(admin.getByText(`${name} archived`).first()).toBeVisible();
    await member.reload();
    await expect(member.getByRole("navigation", { name: "Groups" })).toBeVisible();
    await expect(member.getByRole("link", { name: new RegExp(name) })).toHaveCount(0);
    await member.close();
    await admin.close();
  });
});
