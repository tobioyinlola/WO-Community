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
    await expect(page.getByRole("navigation", { name: "Admin sections" })).toHaveCount(0);
    const key = (await page.locator("code").first().innerText()).trim();
    await page.getByLabel("Code from the app").fill(await freshCode(key));
    await page.getByRole("button", { name: "Turn on two step sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Keep these recovery codes" })).toBeVisible();
    await page.getByRole("button", { name: "I have saved them" }).click();
    const nav = page.getByRole("navigation", { name: "Admin sections" });
    await expect(nav.getByRole("button", { name: "Jobs" })).toBeVisible();
    await expect(nav.getByRole("button", { name: "Members" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test("the overview shows what is waiting", async ({ page }) => {
    const problems = watchConsole(page);
    await signInAdmin(page);
    await expect(page.getByText("Pending approvals").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Needs your attention" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dynamics" })).toBeVisible();
    await expect(page.getByRole("listbox", { name: /one column for each day/ })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("a member can be suspended and reinstated, and the editor's two step sign in reset", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members?q=samuel");
    await page.getByRole("button", { name: "Actions for samuel@demo.test" }).click();
    await page.getByRole("menuitem", { name: "Suspend" }).click();
    await page.getByLabel("Reason").fill("Checking the console");
    await page.getByRole("button", { name: "Suspend", exact: true }).click();
    await expect(page.getByText("Member suspended")).toBeVisible();
    await page.getByRole("button", { name: "Actions for samuel@demo.test" }).click();
    await page.getByRole("menuitem", { name: "Reinstate" }).click();
    await page.getByRole("button", { name: "Reinstate", exact: true }).click();
    await expect(page.getByText("Member reinstated")).toBeVisible();

    await page.goto("/admin/members?q=editor");
    await page.getByRole("button", { name: `Actions for ${EDITOR}` }).click();
    await page.getByRole("menuitem", { name: "Reset two step sign in" }).click();
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText("Two step sign in reset")).toBeVisible();
  });

  test("invitations can be sent and withdrawn", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/invitations");
    const email = `invitee${Date.now()}@demo.test`;
    const box = page.getByLabel("Email addresses");
    await box.fill(email);
    await box.press("Enter");
    await page.getByRole("button", { name: "Send 1 invitation" }).click();
    await expect(page.getByText("1 sent, 0 skipped")).toBeVisible();
    await page.getByRole("button", { name: `Withdraw the invitation to ${email}` }).click();
    await page.getByRole("button", { name: "Withdraw", exact: true }).click();
    await expect(page.getByText("Invitation withdrawn")).toBeVisible();
  });

  test("a waiting job is published", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/jobs?tab=pending");
    await page.locator("button.wo-linkbtn").first().click();
    await page.getByRole("button", { name: "Approve", exact: true }).first().click();
    await page.getByRole("button", { name: "Approve", exact: true }).last().click();
    await expect(page.getByText("Job approved and live")).toBeVisible();
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

  test("the sidebar collapses to a rail, remembers it, and a flyout lists a group's pages", async ({ page }) => {
    await signInAdmin(page);
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect(page.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
    await page.reload();
    await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
    await page.getByRole("button", { name: "Members", exact: true }).hover();
    await expect(page.getByRole("menuitem", { name: /Approvals/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("[");
    await expect(page.getByRole("button", { name: "Collapse sidebar" })).toBeVisible();
  });

  test("search finds a page by keyboard, and members and courses in their groups", async ({ page }) => {
    await signInAdmin(page);
    await page.keyboard.press("Control+k");
    const search = page.getByRole("combobox", { name: "Search" });
    await expect(search).toBeFocused();
    await search.pressSequentially("invit");
    await page.getByRole("option", { name: /Invite someone/ }).click();
    await expect(page).toHaveURL(/\/admin\/invitations/);

    await page.locator("main").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    await search.pressSequentially("amaka");
    await expect(page.getByRole("group", { name: "Members" }).getByRole("option").first()).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/admin\/search\?q=amaka/);
    await expect(page.getByRole("heading", { level: 1, name: /Results for/ })).toBeVisible();
  });

  test("members can be filtered, sorted and selected for bulk actions", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/members");
    await page.getByLabel("Status", { exact: true }).selectOption("pending");
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page.getByRole("button", { name: "Remove filter Status: Pending" })).toBeVisible();
    await page.getByRole("button", { name: "Member", exact: true }).click();
    await expect(page).toHaveURL(/sort=email/);
    await page.getByRole("checkbox", { name: /^Select / }).first().check();
    await expect(page.getByRole("region", { name: "Actions for the selected rows" })).toBeVisible();
    await page.getByRole("button", { name: "Clear all" }).first().click();
    await expect(page.getByRole("button", { name: "Remove filter Status: Pending" })).toHaveCount(0);
  });

  test("a request opens in the drawer, can be stepped through, and a decision can be undone", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/approvals");
    const drawer = page.getByRole("dialog");
    // The list can still be settling right after it appears, so click again until the drawer opens.
    await expect(async () => {
      // Not the seeded pending member the sign-in test needs: use a named applicant.
      await page.locator("tbody tr").filter({ hasText: "Ifeoma Eze" }).click();
      await expect(drawer.getByText(/^Request /)).toBeVisible({ timeout: 3_000 });
    }).toPass({ timeout: 20_000 });
    await expect(drawer.getByRole("heading", { level: 2 })).toBeVisible();
    await page.keyboard.press("j");
    await page.keyboard.press("k");
    await drawer.getByRole("button", { name: "Reject" }).click();
    await drawer.getByLabel("Why are you rejecting this request?").fill("Not a fit for the community");
    await drawer.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(page.getByText(/^Rejecting /)).toBeVisible();
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await page.keyboard.press("Escape");
  });

  test("a request is approved from the keyboard once the undo window has passed", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/approvals");
    await expect(async () => {
      await page.locator("tbody tr").filter({ hasText: "Kofi Annan-Boateng" }).click();
      await expect(page.getByRole("dialog").getByRole("button", { name: "Approve" })).toBeVisible({ timeout: 3_000 });
    }).toPass({ timeout: 20_000 });
    await page.keyboard.press("a");
    await expect(page.getByText(/^Approving /)).toBeVisible();
    await expect(page.getByText(/ approved$/)).toBeVisible({ timeout: 30_000 });
  });

  test("settings show the job board and the appearance choices", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/settings?section=community");
    const waits = page.getByLabel("New jobs wait for an admin before they go live");
    const was = await waits.isChecked();
    await waits.setChecked(!was);
    await expect(page.getByRole("region", { name: "Unsaved changes" })).toBeVisible();
    await page.getByRole("button", { name: "Discard" }).click();
    await expect(page.getByRole("region", { name: "Unsaved changes" })).toHaveCount(0);
    await page.goto("/admin/settings?section=appearance");
    // The product is light only for now, so there is no theme choice to make.
    await expect(page.getByRole("heading", { name: "Theme" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Table density" })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("the design page shows the components in both themes", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/admin/design");
    await expect(page.getByRole("heading", { level: 1, name: "Admin design" })).toBeVisible();
    await expect(page.locator("[data-theme=dark].adm-frame").first()).toBeVisible();
  });

  test("the code generator matches the published test vector", async () => {
    // RFC 6238: key "12345678901234567890" at 59 seconds gives 94287082, so 287082 with six digits.
    expect(totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59_000)).toBe("287082");
  });
});
