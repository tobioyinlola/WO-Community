import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAdmin, watchConsole } from "./helpers";

const SHOTS = process.env.E2E_SHOTS ?? "";

async function firstCourse(page: Page): Promise<string> {
  await page.goto("/app/learn");
  const link = page.locator('a[href^="/app/learn/courses/"]').first();
  await expect(link).toBeVisible();
  return (await link.getAttribute("href")) ?? "";
}

test.describe("sharing", () => {
  test("a member shares a course to the feed, and members open it from there", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    const path = await firstCourse(page);
    await page.goto(path);
    const title = (await page.getByRole("heading", { level: 1 }).innerText()).trim();
    await page.getByRole("button", { name: "Share", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Share this course" });
    await expect(dialog.getByText(title).first()).toBeVisible();
    const words = `Worth taking ${Date.now()}`;
    await dialog.getByLabel("Add a few words (optional)").fill(words);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/share-dialog.png` });
    await dialog.getByRole("button", { name: "Post to the feed" }).click();
    await expect(page.getByText("Shared to the community feed")).toBeVisible();

    await page.goto("/app/feed");
    const post = page.getByRole("article").filter({ hasText: words });
    await expect(post.getByRole("link", { name: `View course: ${title}` })).toBeVisible();
    if (SHOTS) await post.screenshot({ path: `${SHOTS}/share-feed-card.png` });
    await post.getByRole("link", { name: `View course: ${title}` }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    expect(problems).toEqual([]);
  });

  test("a course shared outside shows its brief, and the rest asks to become a member", async ({ page, browser, request }) => {
    await signIn(page);
    const path = await firstCourse(page);
    await page.goto(path);
    const title = (await page.getByRole("heading", { level: 1 }).innerText()).trim();
    await page.getByRole("button", { name: "Share", exact: true }).click();
    const link = await page.getByRole("dialog", { name: "Share this course" }).getByLabel("Link to share").inputValue();
    expect(link).toMatch(/\/s\/course\/[^/]+$/);

    // What chat apps and social sites read to draw the preview.
    const html = await (await request.get(link)).text();
    expect(html).toContain(`<meta property="og:title" content="${title.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}">`);
    expect(html).toContain('property="og:image"');

    // Someone who is not a member follows the link.
    const visitor = await browser.newPage();
    await visitor.goto(link);
    await expect(visitor).toHaveURL(/\/p\/course\//);
    await expect(visitor.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(visitor.getByText("The full course is for members")).toBeVisible();
    await expect(visitor.getByRole("article").getByRole("link", { name: /^Become a member/ })).toHaveAttribute("href", "/register");
    if (SHOTS) await visitor.screenshot({ path: `${SHOTS}/share-teaser.png`, fullPage: true });

    // A member who signs in from there lands on the course itself.
    await visitor.getByRole("article").getByRole("link", { name: "Sign in" }).click();
    await visitor.getByLabel("Email").fill("amaka@demo.test");
    await visitor.getByLabel("Password").fill("Demo-Passw0rd-2026");
    await visitor.getByRole("button", { name: "Sign in" }).click();
    await expect(visitor).toHaveURL(new RegExp(`${path}$`));
    await visitor.close();
  });

  test("an event and a post can be shared outside too", async ({ page, browser }) => {
    await signIn(page);
    await page.goto("/app/events");
    await page.locator('a[href^="/app/events/"]').first().click();
    await page.getByRole("button", { name: "Share", exact: true }).click();
    const eventLink = await page.getByRole("dialog", { name: "Share this event" }).getByLabel("Link to share").inputValue();
    await page.keyboard.press("Escape");

    await page.goto("/app/feed");
    const words = `We closed our round ${Date.now()}`;
    await page.getByPlaceholder(/What are you working on/).fill(words);
    await page.getByRole("button", { name: "Post", exact: true }).click();
    const post = page.getByRole("article").filter({ hasText: words });
    await post.getByRole("button", { name: "Share" }).click();
    const share = page.getByRole("dialog", { name: "Share this post" });
    await expect(share.getByRole("button", { name: "Post to the feed" })).toHaveCount(0);
    const postLink = await share.getByLabel("Link to share").inputValue();
    expect(postLink).toMatch(/\/s\/post\/[0-9a-f-]{36}$/);

    const visitor = await browser.newPage();
    await visitor.goto(eventLink);
    await expect(visitor.getByText("The full event is for members")).toBeVisible();
    await visitor.goto(postLink);
    await expect(visitor.getByText(words)).toBeVisible();
    await expect(visitor.getByText("The full post is for members")).toBeVisible();
    await visitor.close();
  });

  test("an admin shares a course from the console as the team, pinned to the top of the feed", async ({ page, browser }) => {
    await signInAdmin(page);
    await page.goto("/admin/courses");
    // A published course's own page in the console.
    await page.getByRole("tab", { name: "Published" }).click();
    await page.locator('a[href^="/admin/courses/"]').first().click();
    await expect(page.getByRole("button", { name: "Share", exact: true })).toBeVisible();
    const title = (await page.getByRole("heading", { level: 1 }).innerText()).trim();
    await page.getByRole("button", { name: "Share", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Share this course" });
    await expect(dialog.getByLabel("Post as the WO Community team")).toBeChecked();
    const words = `New on the platform ${Date.now()}`;
    await dialog.getByLabel("Add a few words (optional)").fill(words);
    await dialog.getByLabel("Pin it to the top of the feed").check();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/share-admin.png` });
    await dialog.getByRole("button", { name: "Post to the feed" }).click();
    await expect(page.getByText("Shared to the community feed and pinned")).toBeVisible();

    // Members see it at the top, from the team, with the course card.
    const member = await browser.newPage();
    await signIn(member);
    await member.goto("/app/feed");
    const post = member.getByRole("article").filter({ hasText: words }).first();
    await expect(post.getByText("WO Community team").first()).toBeVisible();
    await expect(post.getByText("Pinned")).toBeVisible();
    await expect(post.getByRole("link", { name: `View course: ${title}` })).toBeVisible();
    await member.close();
  });
});
