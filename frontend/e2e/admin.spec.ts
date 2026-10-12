import { expect, test } from "@playwright/test";
import { signIn, signInAdmin, watchConsole } from "./helpers";
import { freshCode, totp } from "./totp";

test.describe.configure({ mode: "serial" });

const EDITOR = "editor@demo.test";

test.describe("the admin console", () => {
  test("a member is sent back to the community", async ({ page }) => {
    await signIn(page);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/app$/);
  });

  test("an editor must set up two step sign in before anything opens, then can use their sections", async ({ page }) => {
    const problems = watchConsole(page);
    await signIn(page, EDITOR);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: "Set up two step sign in" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Admin" })).toHaveCount(0);
    const key = (await page.locator("code").first().innerText()).trim();
    await page.getByLabel("Code from the app").fill(await freshCode(key));
    await page.getByRole("button", { name: "Turn on two step sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Keep these recovery codes" })).toBeVisible();
    await page.getByRole("button", { name: "I have saved them" }).click();
    const nav = page.getByRole("navigation", { name: "Admin" });
    await expect(nav.getByRole("link", { name: "Jobs" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Members" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test("the overview shows what is waiting", async ({ page }) => {
    const problems = watchConsole(page);
    await signInAdmin(page);
    await expect(page.getByText("Waiting for approval")).toBeVisible();
    await expect(page.getByText("Open reports")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Community" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a member can be suspended and reinstated, and the editor's two step sign in reset", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members?q=samuel");
    await page.getByRole("button", { name: "Suspend samuel@demo.test" }).click();
    await page.getByLabel("Reason").fill("Checking the console");
    await page.getByRole("button", { name: "Suspend", exact: true }).click();
    await expect(page.getByText("Member suspended")).toBeVisible();
    await page.getByRole("button", { name: "Reinstate samuel@demo.test" }).click();
    await page.getByRole("button", { name: "Reinstate", exact: true }).click();
    await expect(page.getByText("Member reinstated")).toBeVisible();

    await page.goto("/admin/members?q=editor");
    await page.getByRole("button", { name: `Reset two step sign in for ${EDITOR}` }).click();
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText("Two step sign in reset")).toBeVisible();
  });

  test("invitations can be sent and withdrawn", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/invitations");
    const email = `invitee${Date.now()}@demo.test`;
    await page.getByLabel("Email address").fill(email);
    await page.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText(`Invitation sent to ${email}`)).toBeVisible();
    await page.getByRole("button", { name: `Withdraw the invitation to ${email}` }).click();
    await page.getByRole("button", { name: "Withdraw", exact: true }).click();
    await expect(page.getByText("Invitation withdrawn")).toBeVisible();
  });

  test("a waiting job is published", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/jobs");
    await page.getByRole("button", { name: "Publish" }).first().click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Job published")).toBeVisible();
  });

  test("a report is acted on and a win is published", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/reports");
    await page.getByRole("button", { name: "Hide the content" }).first().click();
    await page.getByLabel("Reason").fill("Spam");
    await page.getByRole("button", { name: "Hide", exact: true }).click();
    await expect(page.getByText("Content hidden")).toBeVisible();
    await page.goto("/admin/wins");
    await page.getByRole("button", { name: "Publish" }).first().click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Win published")).toBeVisible();
  });

  test("a story is written, edited, published and taken down", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/news");
    const title = `E2E story ${Date.now()}`;
    await page.getByRole("button", { name: "New story" }).first().click();
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page.getByLabel("Story", { exact: true }).fill("First paragraph.\n\nSecond paragraph.");
    await page.getByRole("button", { name: "Save as draft" }).click();
    await expect(page.getByText("Draft created")).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: title });
    await card.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Title", { exact: true }).fill(`${title} edited`);
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Story saved")).toBeVisible();
    const edited = page.getByRole("listitem").filter({ hasText: `${title} edited` });
    await edited.getByRole("button", { name: "Publish now" }).click();
    await page.getByRole("button", { name: "Publish", exact: true }).click();
    await expect(page.getByText("Story published")).toBeVisible();
    await edited.getByRole("button", { name: "Take down" }).click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText("Story taken down")).toBeVisible();
  });

  test("an event is created, published and cancelled with a reason", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/events");
    const title = `E2E meetup ${Date.now()}`;
    const day = new Date(Date.now() + 300 * 86_400_000).toISOString().slice(0, 10);
    await page.getByRole("button", { name: "New event" }).first().click();
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page.getByLabel("What it is", { exact: true }).fill("An evening to meet other founders.");
    await page.getByLabel("Starts", { exact: true }).fill(`${day}T18:00`);
    await page.getByLabel("Ends", { exact: true }).fill(`${day}T20:00`);
    await page.getByLabel("Where (place or Online)", { exact: true }).fill("Lagos");
    await page.getByRole("button", { name: "Save as draft" }).click();
    await expect(page.getByText("Draft created")).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: title });
    await expect(card.getByText("18:00 WAT")).toBeVisible();
    await card.getByRole("button", { name: "Publish" }).click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Event published")).toBeVisible();
    await card.getByRole("button", { name: "Cancel event" }).click();
    await page.getByLabel("Reason", { exact: true }).fill("Venue fell through");
    await page.getByRole("button", { name: "Cancel the event" }).click();
    await expect(page.getByText("Event cancelled")).toBeVisible();
  });

  test("a course gets a module and a lesson, is published, taken down and deleted", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/courses");
    const title = `E2E course ${Date.now()}`;
    await page.getByRole("button", { name: "New course" }).first().click();
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page.getByLabel("What it covers", { exact: true }).fill("A short course for the browser tests.");
    await page.getByLabel("Taught by", { exact: true }).fill("Ada Nwosu");
    await page.getByLabel("Category", { exact: true }).fill("Testing");
    await page.getByRole("button", { name: "Save as draft" }).click();
    await expect(page.getByText("Draft created")).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: title });
    await card.getByRole("button", { name: "Lessons" }).click();
    await page.getByLabel("New module", { exact: true }).fill("Start here");
    await page.getByRole("button", { name: "Add module" }).click();
    await page.getByRole("button", { name: "Add a lesson" }).click();
    await page.getByLabel("Title", { exact: true }).fill("Welcome");
    await page.getByLabel("Text", { exact: true }).fill("Welcome to the course.");
    await page.getByRole("button", { name: "Add lesson" }).click();
    await expect(page.getByText("Welcome", { exact: false }).first()).toBeVisible();
    await page.getByRole("button", { name: "Done" }).click();
    await card.getByRole("button", { name: "Publish" }).click();
    await page.getByRole("button", { name: "Publish", exact: true }).last().click();
    await expect(page.getByText("Course published")).toBeVisible();
    await card.getByRole("button", { name: "Take down" }).click();
    await page.getByRole("button", { name: "Take down", exact: true }).last().click();
    await expect(page.getByText("Course taken down")).toBeVisible();
    await card.getByRole("button", { name: `Delete ${title}` }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Course deleted")).toBeVisible();
  });

  test("an audience is saved and counted, and a newsletter draft is made and deleted", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/email");
    await page.getByRole("tab", { name: "Audiences" }).click();
    const audience = `E2E audience ${Date.now()}`;
    await page.getByRole("button", { name: "New audience" }).first().click();
    await page.getByLabel("Name", { exact: true }).fill(audience);
    await page.getByRole("button", { name: "Mentor", exact: true }).click();
    await page.getByRole("button", { name: "How many people is that?" }).click();
    await expect(page.getByRole("status").filter({ hasText: "match" })).toBeVisible();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Audience saved")).toBeVisible();

    await page.getByRole("tab", { name: "Newsletters" }).click();
    const name = `E2E newsletter ${Date.now()}`;
    await page.getByRole("button", { name: "New newsletter" }).first().click();
    await page.getByLabel("Name (only you see this)", { exact: true }).fill(name);
    await page.getByLabel("Subject line", { exact: true }).fill("Hello {{first_name}}");
    await page.getByLabel("Who gets it", { exact: true }).selectOption({ label: audience });
    await page.getByRole("button", { name: "Add paragraph" }).click();
    await page.getByLabel("Text", { exact: true }).fill("This is a test newsletter.");
    await page.getByRole("button", { name: "Save as draft" }).click();
    await expect(page.getByText("Draft created")).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: name });
    await card.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Draft deleted")).toBeVisible();

    await page.getByRole("tab", { name: "Audiences" }).click();
    await page.getByRole("button", { name: `Delete ${audience}` }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Audience deleted")).toBeVisible();
  });

  test("a list entry is added, renamed, retired and deleted", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/lists");
    const name = `E2E sector ${Date.now()}`;
    await page.getByRole("button", { name: "Add an entry" }).click();
    await page.getByLabel("Name", { exact: true }).fill(name);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Entry added")).toBeVisible();
    await page.getByRole("button", { name: `Rename ${name}` }).click();
    await page.getByLabel("Name", { exact: true }).fill(`${name} renamed`);
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Name changed")).toBeVisible();
    await page.getByRole("button", { name: `Retire ${name} renamed` }).click();
    await expect(page.getByRole("row").filter({ hasText: `${name} renamed` }).getByText("Retired", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: `Delete ${name} renamed` }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Entry deleted")).toBeVisible();
  });

  test("the code generator matches the published test vector", async () => {
    // RFC 6238: key "12345678901234567890" at 59 seconds gives 94287082, so 287082 with six digits.
    expect(totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59_000)).toBe("287082");
  });
});
