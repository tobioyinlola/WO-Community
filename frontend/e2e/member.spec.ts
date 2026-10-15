import { expect, test } from "@playwright/test";
import { MENTOR, signIn, watchConsole } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("a signed-in member", () => {
  test("home shows the welcome, the checklist and what is coming up", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening), Amaka/);
    await expect(page.getByText("Finish setting up")).toBeVisible();
    await expect(page.getByText("Demo Day, Lagos")).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("the sidebar collapses to a rail and the slash key goes to search", async ({ page }) => {
    await signIn(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByText("Directory")).toBeVisible();
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect(nav.getByText("Directory")).toBeHidden();
    await expect(nav.getByRole("link", { name: "Directory" })).toBeVisible();
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    await expect(nav.getByText("Directory")).toBeVisible();
    await page.locator("main").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    await expect(page.getByRole("combobox", { name: "Search" })).toBeFocused();
  });

  test("every section of the sidebar opens without errors", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page);
    const sections: Array<[string, string]> = [
      ["Feed", "Community feed"],
      ["Directory", "Find people and startups"],
      ["Jobs", "Jobs and opportunities"],
      ["Events", "Events"],
      ["Learn", "Courses"],
      ["Mentors", "Find a mentor"],
      ["News", "Community news"],
    ];
    for (const [link, heading] of sections) {
      await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: link }).click();
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    }
    expect(problems).toEqual([]);
  });

  test("a post can be written, liked, commented on and deleted", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/feed");
    const text = `E2E post ${Date.now()}`;
    await page.getByLabel("Share with the community").fill(text);
    await page.getByRole("button", { name: "Post", exact: true }).click();
    const card = page.getByRole("article").filter({ hasText: text });
    await expect(card).toBeVisible();

    await card.getByRole("button", { name: /^Like/ }).click();
    await expect(card.getByRole("button", { name: "Like, 1" })).toHaveAttribute("aria-pressed", "true");

    await card.getByRole("button", { name: "Comment" }).first().click();
    await card.getByLabel("Add a comment").fill("A comment from the test");
    await card.getByRole("button", { name: "Comment", exact: true }).last().click();
    await expect(card.getByText("A comment from the test")).toBeVisible();

    await card.getByRole("button", { name: "Delete post" }).click();
    await expect(page.getByText(text)).toHaveCount(0);
  });

  test("a job can be saved and then found under saved jobs", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/jobs");
    await page.getByRole("button", { name: "Save this job" }).first().click();
    await expect(page.getByRole("button", { name: "Remove from saved jobs" }).first()).toBeVisible();
    await page.getByRole("tab", { name: "Saved" }).click();
    await expect(page.getByRole("list").getByRole("link").first()).toBeVisible();
    await page.getByRole("button", { name: "Remove from saved jobs" }).first().click();
  });

  test("posting a job validates, then submits", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/jobs/new");
    await page.getByLabel("Job title").fill("Community manager");
    await page.getByLabel("Description").fill("Look after our members and events.\n\nYou will be the first hire.");
    await page.getByLabel("Application email").fill("jobs@kudafoods.test");
    await page.getByRole("button", { name: "Post job" }).click();
    await expect(page).toHaveURL(/\/app\/jobs\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Community manager");
  });

  test("registering for an event and cancelling again", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/events");
    await page.getByRole("link", { name: /Fundraising basics/ }).click();
    const register = page.getByRole("button", { name: "Register" });
    await expect(register.or(page.getByText("You are registered"))).toBeVisible();
    if (await register.isVisible()) await register.click();
    await expect(page.getByText("You are registered").first()).toBeVisible();
    await page.getByRole("button", { name: "Cancel my place" }).click();
    await expect(page.getByRole("button", { name: "Register" })).toBeVisible();
  });

  test("the slash key searches, and a member is opened from the results by keyboard", async ({ page }) => {
    await signIn(page);
    await page.locator("main").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    const search = page.getByRole("combobox", { name: "Search" });
    await expect(search).toBeFocused();
    await search.pressSequentially("Ngozi");
    const members = page.getByRole("group", { name: "Members" });
    await expect(members.getByRole("option", { name: /Ngozi Eze/ })).toBeVisible();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Ngozi Eze");
  });

  test("see all results opens the results page with filters", async ({ page }) => {
    await signIn(page);
    await page.getByRole("combobox", { name: "Search" }).fill("Ngozi");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/app\/search\?q=Ngozi/);
    await expect(page.getByRole("heading", { level: 1, name: /Results for/ })).toBeVisible();
    await page.getByRole("button", { name: /^Members/ }).click();
    await expect(page).toHaveURL(/type=members/);
    await page.getByRole("link", { name: /Ngozi Eze/ }).first().click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Ngozi Eze");
  });

  test("the bell opens a popover, and View all goes to the notifications page", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: /^Notifications/ }).click();
    const popover = page.getByRole("dialog", { name: "Notifications" });
    await expect(popover).toBeVisible();
    await expect(popover.getByRole("button", { name: "Mark all as read" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(popover).toBeHidden();
    await page.getByRole("button", { name: /^Notifications/ }).click();
    await popover.getByRole("link", { name: "View all notifications" }).click();
    await expect(page).toHaveURL(/\/app\/notifications/);
  });

  test("the profile saves with the version it was loaded from", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/me");
    const headline = `Founder at Kuda Foods ${Date.now() % 1000}`;
    await page.getByLabel("Headline").fill(headline);
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByText("Profile saved")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Headline")).toHaveValue(headline);
  });

  test("a privacy setting changes and is remembered", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/settings");
    const links = page.getByLabel("Links");
    await links.selectOption("members");
    await expect(page.getByText("Saved").first()).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Links")).toHaveValue("members");
    await page.getByLabel("Links").selectOption("private");
  });
});

test.describe("mentoring", () => {
  test("a member books a mentor and the mentor accepts", async ({ page, browser }) => {
    await signIn(page);
    await page.goto("/app/mentors");
    await page.getByRole("link", { name: /Ada Nwosu/ }).first().click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Ada Nwosu");
    const times = page.getByRole("group", { name: /Times on/ }).first().getByRole("button");
    await times.first().click();
    await page.getByLabel("What do you want help with?").fill(`Pricing ${Date.now()}`);
    await page.getByLabel("Tell them about you and what you hope to cover").fill("I need help setting prices.");
    await page.getByRole("button", { name: "Send request" }).click();
    await expect(page).toHaveURL(/mentors\/sessions/);
    await page.getByRole("tab", { name: "Waiting" }).click();
    await expect(page.getByText("Pricing").first()).toBeVisible();

    // The mentor signs in elsewhere and accepts the request.
    const context = await browser.newContext();
    const other = await context.newPage();
    await signIn(other, MENTOR);
    await other.goto("/app/mentors/sessions");
    await other.getByRole("tab", { name: "Waiting" }).click();
    await other.getByRole("button", { name: "Accept" }).first().click();
    await expect(other.getByText("Done")).toBeVisible();
    await context.close();

    await page.reload();
    await page.getByRole("tab", { name: "Upcoming" }).click();
    await expect(page.getByText("Confirmed").first()).toBeVisible();
  });
});
