import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("course administration", () => {
  test("the wizard creates a draft, the course page manages it, and the draft can be deleted", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/courses");
    await expect(page.getByRole("heading", { level: 1, name: "Courses" })).toBeVisible();
    const title = `E2E course ${Date.now()}`;
    await page.getByRole("button", { name: "Add course" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Add course" });
    await expect(drawer).toBeVisible();

    // Step 1 will not move on until the basics are there.
    await expect(drawer.getByRole("button", { name: "Continue" })).toBeDisabled();
    await drawer.getByLabel("Title", { exact: true }).fill(title);
    await drawer.getByLabel("What it covers", { exact: true }).fill("A short course for the browser tests.");
    // A category not on the list yet is typed in, and joins the list when the course is saved.
    await drawer.getByLabel("Category", { exact: true }).selectOption({ label: "Add a new category…" });
    await drawer.getByLabel("New category name").fill("Testing");
    const axe = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(axe.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
    await drawer.getByRole("button", { name: "Continue" }).click();

    // Step 2: lectures from pasted links.
    await drawer.getByLabel("YouTube links for module 1").fill("https://youtu.be/dQw4w9WgXcQ\nhttps://www.youtube.com/watch?v=9bZkp7q19f0");
    await expect(drawer.getByText("2 lessons")).toBeVisible();
    await drawer.getByRole("button", { name: "Continue" }).click();

    // Step 3: every course is free for now; paid is shown but cannot be chosen.
    await expect(drawer.getByRole("radio", { name: "Free" })).toBeChecked();
    await expect(drawer.getByRole("radio", { name: /Paid/ })).toBeDisabled();
    await drawer.getByRole("button", { name: "Continue" }).click();

    // Step 4: review, then create.
    await expect(drawer.getByText(title)).toBeVisible();
    await drawer.getByRole("button", { name: "Create draft" }).click();
    await expect(page).toHaveURL(/\/admin\/courses\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();

    // A cover image is optional, so a complete draft can be published right away.
    await expect(page.getByText("Before this can be published")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Publish", exact: true })).toBeEnabled();

    // The curriculum has the two lectures; every other tab opens.
    await expect(page.getByText("Section 1: Module 1")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Edit lecture/ })).toHaveCount(2);
    for (const name of ["Learners", "Requests", "Reviews", "Q&A", "Announcements", "Settings"]) {
      await page.getByRole("tab", { name: new RegExp(`^${name}`) }).click();
      await expect(page.getByRole("tabpanel")).toBeVisible();
    }
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByLabel("Subtitle").fill("Added by the browser test");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Course saved")).toBeVisible();

    await page.getByRole("button", { name: "Delete course" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Course deleted")).toBeVisible();
    await expect(page).toHaveURL(/\/admin\/courses$/);
  });

  test("the list filters, and the requests page opens", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/courses");
    await page.getByRole("tab", { name: "Drafts" }).click();
    await expect(page).toHaveURL(/status=draft/);
    await page.getByLabel("Search courses").fill("zzzz no such course");
    await expect(page.getByText("No courses match")).toBeVisible();
    await page.goto("/admin/course-requests");
    await expect(page.getByRole("heading", { level: 1, name: "Enrolment requests" })).toBeVisible();
    await page.getByRole("button", { name: "Approved" }).click();
    await expect(page.getByRole("button", { name: "Approved" })).toHaveAttribute("aria-pressed", "true");
  });

  test("course categories are managed under Lists and offered on every course", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/lists?list=course_categories");
    await expect(page.getByRole("tab", { name: "Course categories" })).toHaveAttribute("aria-selected", "true");
    for (const name of ["Masterclasses", "Investor Classes", "Marketing, Sales and Public Relations", "Project Management", "AI Training", "Finance"]) {
      await expect(page.locator("tbody").getByText(name, { exact: true })).toBeVisible();
    }
    const name = `E2E category ${Date.now()}`;
    await page.getByRole("button", { name: "Add an entry" }).click();
    await page.getByRole("dialog", { name: "Add an entry" }).getByLabel("Name").fill(name);
    await page.getByRole("dialog", { name: "Add an entry" }).getByRole("button", { name: "Add" }).click();
    await expect(page.locator("tbody").getByText(name, { exact: true })).toBeVisible();
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/course-categories.png`, fullPage: true });

    // It is offered at once when a course is made.
    await page.goto("/admin/courses");
    await page.getByRole("button", { name: "Add course" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Add course" });
    await expect(drawer.getByLabel("Category", { exact: true }).locator("option", { hasText: name })).toHaveCount(1);
    await drawer.getByLabel("Category", { exact: true }).selectOption(name);
    if (process.env.E2E_SHOTS) await drawer.screenshot({ path: `${process.env.E2E_SHOTS}/course-category-picker.png` });
    await page.keyboard.press("Escape");

    // Not used by any course, so it can be deleted.
    await page.goto("/admin/lists?list=course_categories");
    await page.getByRole("button", { name: `Delete ${name}` }).click();
    await page.getByRole("dialog", { name: "Delete this entry?" }).getByRole("button", { name: "Delete" }).click();
    await expect(page.locator("tbody").getByText(name, { exact: true })).toHaveCount(0);
  });
});
