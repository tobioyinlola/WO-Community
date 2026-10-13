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
    await drawer.getByLabel("Category", { exact: true }).fill("Testing");
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
    await expect(page.getByText("Section 1: Section 1")).toBeVisible();
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
});
