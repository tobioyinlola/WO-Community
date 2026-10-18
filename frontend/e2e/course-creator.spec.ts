import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const stamp = Date.now();
const MULTI = `Creator journey ${stamp}`;
const SINGLE = `Creator single ${stamp}`;
const VIDEOS = ["https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=aqz-KE-bpKQ", "https://youtu.be/9bZkp7q19f0", "https://www.youtube.com/shorts/jNQXAC9IVRw"];

async function details(page: Page, title: string) {
  await page.goto("/admin/courses");
  await page.getByRole("button", { name: "Add course" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Add course" });
  await expect(drawer.getByRole("list", { name: "Progress" })).toBeVisible();
  await drawer.getByLabel("Title", { exact: true }).fill(title);
  await drawer.getByLabel("What it covers").fill("A course made by the creator test.");
  await drawer.getByLabel("Category").selectOption("Project Management"); // from the category list
  await drawer.getByRole("button", { name: "Continue" }).click();
  return drawer;
}

test.describe("course creator", () => {
  test("an admin builds a three module course, an invalid link is refused, and it is published free", async ({ page }) => {
    await signInAdmin(page);
    const drawer = await details(page, MULTI);

    // Module 1 starts empty; a line that is not YouTube is named and blocks the next step.
    await drawer.getByLabel("YouTube links for module 1").fill(`${VIDEOS[0]}\nhttps://vimeo.com/12345`);
    await expect(drawer.getByText("Line 2 is not a YouTube link")).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Continue" })).toBeDisabled();
    await drawer.getByLabel("YouTube links for module 1").fill(`${VIDEOS[0]}\n${VIDEOS[1]}`);
    await expect(drawer.getByText("not a YouTube link")).toHaveCount(0);

    // Add modules 2, 3 and a spare, delete the spare, move module 3 up.
    for (let i = 0; i < 3; i++) await drawer.getByRole("button", { name: "Add module" }).click();
    await drawer.getByLabel("YouTube links for module 2").fill(VIDEOS[2]);
    await drawer.getByLabel("YouTube links for module 3").fill(VIDEOS[3]);
    page.once("dialog", (d) => void d.accept());
    await drawer.getByRole("button", { name: "Delete module 4" }).click();
    await expect(drawer.getByLabel("YouTube links for module 4")).toHaveCount(0);
    await drawer.getByRole("button", { name: "Move module 3 up" }).click();
    await expect(drawer.getByLabel("YouTube links for module 2")).toHaveValue(VIDEOS[3]);

    await drawer.getByRole("button", { name: "Continue" }).click();
    // Free is chosen; Paid is visible but cannot be picked.
    await expect(drawer.getByRole("radio", { name: "Free" })).toBeChecked();
    await expect(drawer.getByRole("radio", { name: /Paid/ })).toBeDisabled();
    await expect(drawer.getByText("Coming soon")).toBeVisible();
    await drawer.getByRole("button", { name: "Continue" }).click();

    await expect(drawer.getByText("At least one lesson with a YouTube link: done")).toBeVisible();
    const result = await new AxeBuilder({ page }).include("[role=dialog]").withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
    await drawer.getByLabel("Publish as soon as it is created").check();
    await drawer.getByRole("button", { name: "Create and publish" }).click();
    await expect(page.getByRole("heading", { level: 1, name: MULTI })).toBeVisible();
    await expect(page.getByText("Published", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Before this can be published")).toHaveCount(0);
  });

  test("a one video course with no cover image publishes", async ({ page }) => {
    await signInAdmin(page);
    const drawer = await details(page, SINGLE);
    await drawer.getByLabel("YouTube links for module 1").fill(VIDEOS[0]);
    await drawer.getByRole("button", { name: "Continue" }).click();
    await drawer.getByRole("button", { name: "Continue" }).click();
    await drawer.getByLabel("Publish as soon as it is created").check();
    await drawer.getByRole("button", { name: "Create and publish" }).click();
    await expect(page.getByRole("heading", { level: 1, name: SINGLE })).toBeVisible();
    await expect(page.getByText("Published", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/^1 lecture · 0 learners/)).toBeVisible();
  });

  test("a member finds the course, sees no video links, enrols, learns, finishes and gets the certificate", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/learn");
    await page.getByRole("link", { name: new RegExp(SINGLE) }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: SINGLE })).toBeVisible();
    // The outline is visible but there is no video before joining.
    await expect(page.locator("iframe")).toHaveCount(0);
    await expect(page.locator("a[href*='youtu']")).toHaveCount(0);
    await page.getByRole("button", { name: "Enrol for free" }).click();
    await expect(page.getByText("You are enrolled").first()).toBeVisible();
    await page.getByRole("link", { name: /Start learning|Continue learning/ }).click();
    await expect(page.locator("iframe[src*='youtube-nocookie.com']")).toBeVisible();
    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByText("Course complete. Your certificate is ready.")).toBeVisible();
    // The certificate is made by the background worker, so give it a moment.
    await expect(async () => {
      await page.goto("/app/learn/certificates");
      await expect(page.getByText(SINGLE).first()).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 60_000 });

    // Leaving keeps progress: coming back resumes as finished.
    await page.goto("/app/learn");
    await page.getByRole("link", { name: new RegExp(SINGLE) }).first().click();
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Leave course" }).click();
    await expect(page.getByText("You left the course")).toBeVisible();
    await page.getByRole("button", { name: "Enrol for free" }).click();
    await expect(page.getByRole("link", { name: "Review the course" })).toBeVisible();
  });

  test("a draft course is not visible to members, and a live course with learners is archived", async ({ page, browser }, info) => {
    await signInAdmin(page);
    await page.goto("/admin/courses");
    await page.getByRole("link", { name: "Hiring your first ten people" }).first().click();
    const draftId = page.url().split("/").pop() ?? "";
    expect(draftId).not.toEqual("");

    const member = await browser.newContext({ baseURL: info.project.use.baseURL });
    const view = await member.newPage();
    try {
      await signIn(view);
      await view.goto("/app/learn");
      await expect(view.getByRole("link", { name: "Hiring your first ten people" })).toHaveCount(0);
      await view.goto(`/app/learn/courses/${draftId}`);
      await expect(view.getByRole("link", { name: /Start learning|Continue learning/ })).toHaveCount(0);
    } finally {
      await member.close();
    }

    // The single video course is live and has a learner, so Archive is the way to retire it.
    // Both courses made by this file are archived, so reruns leave the catalogue as they found it.
    for (const title of [SINGLE, MULTI]) {
      await page.goto("/admin/courses");
      await page.getByRole("link", { name: title }).first().click();
      await expect(page.getByRole("button", { name: "Delete course" })).toHaveCount(0); // a live course is archived, never deleted
      await page.getByRole("button", { name: "Archive" }).first().click();
      await page.getByRole("dialog").getByRole("button", { name: "Archive" }).click();
      await expect(page).toHaveURL(/\/admin\/courses$/);
      await expect(page.getByRole("link", { name: title })).toHaveCount(0);
    }
  });

  test("the drawer keeps an unfinished draft, and modules can be dragged into order", async ({ page }) => {
    // Tall enough that both modules are on screen at once, as a drag needs.
    await page.setViewportSize({ width: 1280, height: 1600 });
    await signInAdmin(page);
    const drawer = await details(page, `Creator draft ${stamp}`);
    await drawer.getByLabel("YouTube links for module 1").fill(VIDEOS[0]);
    await drawer.getByRole("button", { name: "Add module" }).click();
    await drawer.getByLabel("YouTube links for module 2").fill(VIDEOS[1]);

    // Dragging the second module's handle onto the first puts it first. The buttons still work.
    await drawer.locator(".wo-module__grip").nth(1).dragTo(drawer.locator("fieldset.wo-module").first());
    await expect(drawer.getByLabel("YouTube links for module 1")).toHaveValue(VIDEOS[1]);
    await expect(drawer.getByText("Module moved to position 1 of 2.")).toBeAttached();
    await drawer.getByRole("button", { name: "Move module 1 down" }).click();
    await expect(drawer.getByLabel("YouTube links for module 1")).toHaveValue(VIDEOS[0]);

    // It is saved as it is typed, so closing loses nothing and asks nothing.
    await expect(drawer.getByText("Saved on this device")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Add course" })).toHaveCount(0);

    await page.reload();
    await page.getByRole("button", { name: "Add course" }).first().click();
    const again = page.getByRole("dialog", { name: "Add course" });
    await expect(again.getByText("Picked up the draft you had saved.")).toBeVisible();
    await expect(again.getByLabel("YouTube links for module 2")).toHaveValue(VIDEOS[1]);

    // Start over clears it, and the next opening is a blank form.
    await again.getByRole("button", { name: "Start over" }).click();
    await expect(again.getByLabel("Title", { exact: true })).toHaveValue("");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Add course" }).first().click();
    await expect(page.getByRole("dialog", { name: "Add course" }).getByText("Picked up the draft you had saved.")).toHaveCount(0);
  });
});
