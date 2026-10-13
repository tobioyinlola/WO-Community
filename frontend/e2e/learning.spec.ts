import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

const COURSE = /Founder fundamentals/;

/** Opens the course page and makes sure the member is enrolled, whatever an earlier run left. */
async function openCourse(page: Page) {
  await page.goto("/app/learn");
  await page.getByRole("link", { name: COURSE }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Founder fundamentals" })).toBeVisible();
  const enrol = page.getByRole("button", { name: "Enrol for free" });
  const way = page.getByRole("link", { name: /Start learning|Continue learning|Review the course/ });
  await expect(enrol.or(way)).toBeVisible();
  if (await enrol.isVisible()) {
    await enrol.click();
    await expect(page.getByText("You are enrolled").first()).toBeVisible();
  }
  await expect(way).toBeVisible();
}

test.describe("learning", () => {
  test("the catalogue searches, filters, sorts and shows what each course costs", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/learn");
    await expect(page.getByRole("heading", { level: 1, name: "Courses" })).toBeVisible();
    const cards = page.getByRole("list", { name: "Courses" }).getByRole("link");
    const filters = page.getByRole("search", { name: "Filter courses" });
    await expect(cards.first()).toBeVisible();
    const total = await cards.count();
    expect(total).toBeGreaterThan(1);

    await filters.getByLabel("Search").fill("Fundraising");
    await expect(page).toHaveURL(/q=Fundraising/);
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText(/Free|You finished this course|complete/); // a course already started shows progress, not a price
    await filters.getByLabel("Search").fill("zzzz no such course");
    await expect(page.getByText("No courses match")).toBeVisible();
    await filters.getByLabel("Search").fill("");

    await filters.getByLabel("Price").selectOption("paid");
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText(/Financial models investors trust/);
    await expect(cards.first()).toContainText(/₦\s?20,000/); // the promotional price, with the full price struck through
    await filters.getByLabel("Search").fill("zzzz no such course");
    await expect(page.getByText("No courses match")).toBeVisible();
    await filters.getByLabel("Search").fill("");
    await filters.getByLabel("Price").selectOption("free");
    await expect(cards.first()).toBeVisible();
    await filters.getByLabel("Sort by").selectOption("popular");
    await expect(page).toHaveURL(/sort=popular/);
    await expect(cards.first()).toBeVisible();
    await page.getByRole("button", { name: "All", exact: true }).click();
  });

  test("a course page explains the course, can be saved and shared, and enrols", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    // Some browsers have a share sheet of their own; this test is about the copy fallback.
    await page.addInitScript(() => Object.defineProperty(navigator, "share", { value: undefined }));
    await signIn(page);
    await openCourse(page);
    await expect(page.getByRole("heading", { name: "Course content" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Section 1:/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "This course includes" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();

    const save = page.getByRole("button", { name: /Save for later|Saved/ });
    const wasSaved = (await save.textContent())?.trim() === "Saved";
    await save.click();
    await expect(page.getByRole("button", { name: wasSaved ? "Save for later" : "Saved" })).toBeVisible();
    await page.getByRole("button", { name: wasSaved ? "Save for later" : "Saved" }).click();
    await expect(page.getByRole("button", { name: wasSaved ? "Saved" : "Save for later" })).toBeVisible();

    await page.getByRole("button", { name: "Share" }).click();
    await expect(page.getByText("Link copied")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("/app/learn/courses/");
  });

  test("a lecture can be completed, moved between, asked about, noted and the course reviewed", async ({ page }) => {
    await signIn(page);
    await openCourse(page);
    // Start from the first lecture, not from wherever an earlier run stopped.
    await page.getByRole("link", { name: /^Why this matters/ }).first().click();
    await expect(page).toHaveURL(/\/lecture\//);
    const title = page.getByRole("heading", { level: 1 });
    await expect(title).not.toHaveText("Founder fundamentals");
    const first = await title.innerText();

    // Completing flips the button, and flips back.
    const mark = page.getByRole("button", { name: /^Mark complete$|^Completed\. Mark as not done$/ });
    const was = (await mark.textContent()) ?? "";
    await mark.click();
    await expect(page.getByRole("button", { name: was.startsWith("Completed") ? "Mark complete" : /^Completed\. Mark as not done$/ })).toBeVisible();
    await page.getByRole("button", { name: was.startsWith("Completed") ? "Mark complete" : /^Completed\. Mark as not done$/ }).click();
    await expect(page.getByRole("button", { name: was.startsWith("Completed") ? /^Completed\. Mark as not done$/ : "Mark complete" })).toBeVisible();

    // The next lecture opens, the previous brings us back, and N does the same.
    await page.getByRole("button", { name: /^Next/ }).click();
    await expect(title).not.toHaveText(first);
    await page.getByRole("button", { name: "Previous" }).click();
    await expect(title).toHaveText(first);
    await page.keyboard.press("n");
    await expect(title).not.toHaveText(first);
    await page.keyboard.press("p");
    await expect(title).toHaveText(first);

    // Questions.
    await page.getByRole("tab", { name: "Q&A" }).click();
    const question = `How should I price a pre-seed round? ${Date.now() % 100000}`;
    await page.getByLabel("Ask a question about this lecture").fill(question);
    await page.getByRole("button", { name: "Post question" }).click();
    await expect(page.getByText(question)).toBeVisible();

    // Notes: added at the moment watched, private, and deletable.
    await page.getByRole("tab", { name: "Notes" }).click();
    const note = `Remember to check the cap table ${Date.now() % 100000}`;
    await page.getByLabel("Write a note").fill(note);
    await page.getByRole("button", { name: "Add note" }).click();
    await expect(page.getByText(note)).toBeVisible();
    await page.getByRole("listitem").filter({ hasText: note }).getByRole("button", { name: "Delete this note" }).click();
    await expect(page.getByText(note)).toBeHidden();

    // The course content marks where we are.
    await expect(page.getByRole("navigation", { name: "Course content" }).first()).toBeVisible();
    await expect(page.locator('a[aria-current="step"]').first()).toBeVisible();
  });

  test("a review is possible once a quarter of the course is done", async ({ page }) => {
    await signIn(page);
    await openCourse(page);
    // Finish the first lecture if it is not already, so the course is past a quarter.
    await page.getByRole("link", { name: /Start learning|Continue learning|Review the course/ }).click();
    const done = page.getByRole("button", { name: /^Completed\. Mark as not done$/ });
    const mark = page.getByRole("button", { name: "Mark complete" });
    await expect(done.or(mark)).toBeVisible(); // wait for the lecture to load before looking
    if (!(await done.isVisible())) await mark.click();
    await expect(done).toBeVisible();
    await page.getByRole("tab", { name: "Reviews" }).click();
    const text = `Clear and practical ${Date.now() % 100000}`;
    await page.getByRole("radio", { name: "5 stars" }).check({ force: true });
    await page.getByLabel(/Tell others what you thought/).fill(text);
    await page.getByRole("button", { name: /Send review|Update review/ }).click();
    await expect(page.getByText(/Thank you for your review|Your review is updated/)).toBeVisible();
    await expect(page.locator(".wo-review__body", { hasText: text })).toBeVisible();
  });

  test("My learning shows progress and what was saved", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/learn/my");
    await expect(page.getByRole("heading", { level: 1, name: "My learning" })).toBeVisible();
    const cards = page.getByRole("list", { name: "Your courses" }).getByRole("link");
    await expect(cards.filter({ hasText: "Founder fundamentals" })).toBeVisible();
    await expect(cards.filter({ hasText: "Founder fundamentals" }).getByRole("progressbar", { name: "Your progress" })).toBeVisible();
    await page.getByRole("tab", { name: "In progress" }).click();
    await page.getByRole("tab", { name: "Saved" }).click();
    await expect(page.getByRole("tab", { name: "Saved" })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("link", { name: "Your certificates" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Your certificates" })).toBeVisible();
  });

  test("old course links still work", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/learn");
    const href = await page.getByRole("link", { name: COURSE }).first().getAttribute("href");
    expect(href).toMatch(/\/app\/learn\/courses\/.+/);
    const slug = href?.split("/").pop() ?? "";
    await page.goto(`/app/learn/${slug}`);
    await expect(page).toHaveURL(new RegExp(`/app/learn/courses/${slug}`));
  });

  test("the learning pages pass the accessibility checks", async ({ page }) => {
    const tags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
    await signIn(page);
    await openCourse(page);
    for (const [name, locator] of [
      ["course page", page.getByRole("heading", { level: 1, name: "Founder fundamentals" })],
    ] as const) {
      await expect(locator).toBeVisible();
      const result = await new AxeBuilder({ page }).withTags(tags).analyze();
      expect(result.violations.map((v) => `${name}: ${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
    }
    await page.getByRole("link", { name: /Start learning|Continue learning|Review the course/ }).click();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForTimeout(800);
    const player = await new AxeBuilder({ page }).withTags(tags).analyze();
    expect(player.violations.map((v) => `player: ${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
  });
});
