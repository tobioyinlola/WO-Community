import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { MENTOR, signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function openSettings(page: Page) {
  await page.goto("/app/settings");
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("link", { name: "Mentorship" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Mentorship" })).toBeVisible();
}

const summary = (page: Page) => page.getByRole("status").filter({ hasText: "In summary:" });
const saveBar = (page: Page) => page.getByRole("region", { name: "Unsaved changes" });

test.describe("mentor settings", () => {
  test("the schedule is edited with quick actions, validated, summarised and saved", async ({ page }) => {
    await signIn(page, MENTOR);
    await openSettings(page);
    await expect(saveBar(page)).toBeHidden(); // the bar appears only when something changed

    const week = page.getByRole("list", { name: "Weekly schedule" });
    await expect(summary(page)).toContainText("Tue to Fri, 10:00 to 13:00");

    // Copy Tuesday to every weekday, then add Saturday.
    await page.getByLabel("Copy from").selectOption({ label: "Tuesday" });
    await page.getByRole("button", { name: "Copy to weekdays" }).click();
    await expect(summary(page)).toContainText("Mon to Fri, 10:00 to 13:00");
    await expect(saveBar(page)).toBeVisible();
    await week.getByRole("switch", { name: "Saturday" }).check();
    await expect(summary(page)).toContainText("Sat, 09:00 to 12:00");

    // An overlapping range is explained and blocks saving.
    await page.getByRole("button", { name: "Add a range on Saturday" }).click();
    await page.getByLabel("Saturday range 2 starts").selectOption("11:00");
    await page.getByLabel("Saturday range 2 ends").selectOption("14:00");
    await expect(page.getByRole("alert").filter({ hasText: "Saturday: Ranges must not overlap." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await page.getByRole("button", { name: "Remove Saturday range 2" }).click();
    await expect(page.getByRole("button", { name: "Save changes" })).toBeEnabled();

    const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(result.violations.map((v) => `${v.id} ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

    // Discard puts everything back and hides the bar.
    await saveBar(page).getByRole("button", { name: "Discard" }).click();
    await expect(saveBar(page)).toBeHidden();
    await expect(summary(page)).toContainText("Tue to Fri, 10:00 to 13:00");
  });

  test("session settings and pricing save, and the booking page shows the price and the arrangement", async ({ page, browser }, info) => {
    await signIn(page, MENTOR);
    await openSettings(page);
    await page.getByRole("checkbox", { name: "30 minutes" }).check();
    await page.getByLabel("Buffer between sessions").selectOption("15");
    await page.getByRole("radio", { name: "Paid" }).check();
    await page.getByLabel("Price per session").fill("20000");
    await expect(page.getByText("Payment is arranged directly")).toBeVisible();
    await expect(page.getByLabel("How mentees will see your price")).toContainText("30 minutes");
    await saveBar(page).getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Changes saved")).toBeVisible();
    await expect(saveBar(page)).toBeHidden();

    // The mentor's own preview shows what a mentee will see.
    await page.getByRole("button", { name: "Preview as mentee" }).click();
    const drawer = page.getByRole("dialog", { name: "As a mentee sees it" });
    await expect(drawer.getByRole("group", { name: "Session length" })).toBeVisible();
    await expect(drawer.getByText(/per session/)).toBeVisible();
    await expect(drawer.getByLabel("Time zone")).toBeVisible();
    await page.keyboard.press("Escape");

    // A mentee sees a price, the arrangement, and can pick a length, a day and a time.
    const mentee = await browser.newContext({ baseURL: info.project.use.baseURL });
    const view = await mentee.newPage();
    try {
      await signIn(view);
      await view.goto("/app/mentors");
      await view.getByRole("link", { name: /Ada/ }).first().click();
      await expect(view.getByText(/per session/)).toBeVisible();
      await expect(view.getByText(/Payment arranged directly with the mentor/)).toBeVisible();
      await view.getByRole("button", { name: "30 min" }).click();
      await expect(view.getByRole("button", { name: "30 min" })).toHaveAttribute("aria-pressed", "true");
      await view.getByRole("group", { name: "Days with times" }).getByRole("button").first().click();
      await view.getByRole("group", { name: /^Times on/ }).getByRole("button").first().click();
      const dialog = view.getByRole("dialog", { name: "Request this session" });
      await expect(dialog).toContainText("30 minutes");
      await expect(dialog.getByText("Payment arranged directly")).toBeVisible();
      await dialog.getByRole("button", { name: "Cancel" }).click();
    } finally {
      await mentee.close();
    }
  });

  test("days off are blocked and removed, and the settings go back to how they were", async ({ page }) => {
    await signIn(page, MENTOR);
    await openSettings(page);
    const day = new Date(Date.now() + 12 * 86_400_000).toISOString().slice(0, 10);
    const timeOff = page.getByRole("heading", { name: "Time off and extra time" }).locator("xpath=..");
    await timeOff.getByLabel("First day off").fill(day);
    await timeOff.getByLabel("Note (optional)").fill("Holiday");
    await timeOff.getByRole("button", { name: "Block these days" }).click();
    await expect(page.getByText("Days off saved")).toBeVisible();
    const list = page.getByRole("list", { name: "Days off and extra time" });
    await expect(list).toContainText("Holiday");
    await list.getByRole("button", { name: /^Remove days off from/ }).click();
    await expect(page.getByText("Removed")).toBeVisible();

    // Put the demo mentor back as seeded.
    await page.getByRole("checkbox", { name: "30 minutes" }).uncheck();
    await page.getByLabel("Buffer between sessions").selectOption("0");
    await page.getByRole("radio", { name: "Free" }).check();
    await saveBar(page).getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Changes saved")).toBeVisible();
    await expect(summary(page)).toContainText("Tue to Fri");
  });

  test("a member who is not a mentor does not see the section", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/settings");
    const sections = page.getByRole("navigation", { name: "Settings sections" });
    await expect(sections.getByRole("link", { name: "Privacy and notifications" })).toBeVisible();
    await expect(sections.getByRole("link", { name: "Mentorship" })).toHaveCount(0);
    await page.goto("/app/settings/mentorship");
    await expect(page.getByText("Mentorship settings are for approved mentors")).toBeVisible();
  });
});
