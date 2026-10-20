import { expect, test } from "@playwright/test";
import { MENTOR, signIn, watchConsole } from "./helpers";

test.describe("links in the feed", () => {
  test("a pasted address is a link that opens in a new tab, with a card that names the site", async ({ browser }) => {
    const author = await browser.newPage();
    const problems = watchConsole(author);
    await signIn(author);
    await author.goto("/app/feed");
    const stamp = Date.now();
    const address = `https://example.com/guides/fundraising?ref=wo-${stamp}`;
    const words = `Worth a read ${stamp}: ${address}, and also www.example.org/tools-${stamp}.`;
    await author.getByLabel("Share with the community").fill(words);
    await author.getByRole("button", { name: "Post", exact: true }).click();

    const post = author.getByRole("article").filter({ hasText: `Worth a read ${stamp}` }).first();
    await expect(post).toBeVisible();
    // Both addresses are real links that leave in a new tab; the full stop is not part of the link.
    const first = post.locator(".app-richtext a", { hasText: address });
    await expect(first).toHaveAttribute("href", address);
    await expect(first).toHaveAttribute("target", "_blank");
    const second = post.locator(".app-richtext a", { hasText: `www.example.org/tools-${stamp}` });
    await expect(second).toHaveAttribute("href", `https://www.example.org/tools-${stamp}`);

    // Each address has a card before it is opened, even if its page could not be read.
    const cards = post.locator("a.wo-linkcard");
    await expect(cards).toHaveCount(2);
    // (What a card says depends on whether the page could be read; it always says something.)
    await expect(cards.first()).toHaveAttribute("href", address);
    await expect(cards.first()).toHaveAttribute("target", "_blank");
    await expect(cards.first()).not.toHaveText("");
    await expect(cards.nth(1)).toHaveAttribute("href", `https://www.example.org/tools-${stamp}`);

    // Another member sees the same, and a comment's link is clickable too.
    const reader = await browser.newPage();
    await signIn(reader, MENTOR);
    await reader.goto("/app/feed");
    const seen = reader.getByRole("article").filter({ hasText: `Worth a read ${stamp}` }).first();
    await expect(seen.locator("a.wo-linkcard")).toHaveCount(2);
    await seen.locator("button.app-react", { hasText: /comment/i }).click();
    await seen.getByLabel("Add a comment").fill("Also see https://example.net/notes");
    await seen.getByRole("button", { name: "Comment", exact: true }).last().click();
    await expect(seen.locator('.app-richtext a[href="https://example.net/notes"]')).toBeVisible();
    expect(problems).toEqual([]);
    await reader.close();
    await author.close();
  });
});
