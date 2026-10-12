import { expect, test, type Browser } from "@playwright/test";
import { signIn, signInAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

const PAID = "Financial models investors trust";

async function otherPerson(browser: Browser, baseURL: string | undefined) {
  const context = await browser.newContext({ baseURL });
  return { page: await context.newPage(), close: () => context.close() };
}

test.describe("journeys that cross roles", () => {
  test("a member asks for a paid course, an admin approves, and the member can start", async ({ page, browser }, info) => {
    // The member finds the paid course and asks for access instead of buying it.
    await signIn(page);
    await page.goto("/app/learn");
    await page.getByRole("link", { name: new RegExp(PAID) }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: PAID })).toBeVisible();
    await expect(page.getByText(/₦|NGN/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Enrol for free" })).toHaveCount(0);
    await page.getByRole("button", { name: "Request access" }).click();
    await page.getByLabel(/Anything you would like us to know/).fill("I am preparing a seed round.");
    await page.getByRole("dialog", { name: "Request access" }).getByRole("button", { name: "Send request" }).click();
    await expect(page.getByRole("button", { name: "Request sent" })).toBeDisabled();

    // An admin sees it with the other waiting requests and approves it.
    const admin = await otherPerson(browser, info.project.use.baseURL);
    try {
      await signInAdmin(admin.page);
      await admin.page.goto("/admin/course-requests");
      await expect(admin.page.getByRole("heading", { level: 1, name: "Enrolment requests" })).toBeVisible();
      await admin.page.getByRole("button", { name: "Approve Amaka Obi" }).click();
      await expect(admin.page.getByRole("button", { name: "Approve Amaka Obi" })).toHaveCount(0);

      // The member now has the course. The notice goes out through the worker, so it is not checked here.
      await page.reload();
      await expect(page.getByRole("link", { name: /Start learning|Continue learning/ })).toBeVisible();

      // Put the demo community back: remove the learner again.
      await admin.page.goto("/admin/courses");
      await admin.page.getByRole("link", { name: PAID }).first().click();
      await admin.page.getByRole("tab", { name: /^Learners/ }).click();
      await admin.page.getByRole("button", { name: "Remove Amaka Obi from this course" }).click();
      await admin.page.getByRole("button", { name: "Remove", exact: true }).click();
      await expect(admin.page.getByText("Learner removed")).toBeVisible();
    } finally {
      await admin.close();
    }
  });

  test("two mentees choose the same time and only the first is booked", async ({ page, browser }, info) => {
    const visit = async (who: Awaited<ReturnType<typeof otherPerson>>["page"]) => {
      await who.goto("/app/mentors");
      await who.getByRole("link", { name: /Ada Nwosu/ }).first().click();
      await expect(who.getByRole("heading", { level: 1 })).toContainText("Ada Nwosu");
      await who.getByRole("group", { name: /Times on/ }).first().getByRole("button").first().click();
      return who.getByRole("dialog", { name: "Request this session" });
    };
    const second = await otherPerson(browser, info.project.use.baseURL);
    try {
      await signIn(page);
      await signIn(second.page, "tunde@demo.test");
      // Both have the same time open before either sends.
      const first = await visit(page);
      const late = await visit(second.page);
      for (const [dialog, who] of [[first, "first"], [late, "second"]] as const) {
        await dialog.getByLabel("What do you want help with?").fill(`Race ${who} ${Date.now()}`);
        await dialog.getByLabel("Tell them about you and what you hope to cover").fill("Choosing a pricing model.");
      }
      await first.getByRole("button", { name: "Send request" }).click();
      await expect(page).toHaveURL(/mentors\/sessions/);

      // The second is told plainly, keeps what they typed, and can pick another time.
      await late.getByRole("button", { name: "Send request" }).click();
      await expect(late.getByText("That time is no longer available")).toBeVisible();
      await expect(late.getByLabel("What do you want help with?")).toHaveValue(/Race second/);
      await late.getByRole("button", { name: "Cancel" }).click();
      await second.page.goto("/app/mentors/sessions");
      await second.page.getByRole("tab", { name: "Waiting" }).click();
      await expect(second.page.getByText(/Race second/)).toHaveCount(0);

      // Put things back: the first mentee withdraws their request.
      await page.getByRole("tab", { name: "Waiting" }).click();
      const card = page.getByText(/Race first/).locator("xpath=ancestor::*[.//button[normalize-space()='Withdraw']][1]");
      await card.getByRole("button", { name: "Withdraw" }).click();
      await page.getByRole("button", { name: "Cancel session" }).click();
      await expect(page.getByText(/Race first/)).toHaveCount(0);
    } finally {
      await second.close();
    }
  });

  test("the referrer sees who joined through them, and the admin can search for a support request", async ({ page, browser }, info) => {
    await signIn(page);
    const card = page.locator("section").filter({ has: page.getByRole("heading", { name: "Your referrals" }) });
    await expect(card).toContainText("Tunde Kolade");
    await expect(card).toContainText("Ngozi Eze");

    const admin = await otherPerson(browser, info.project.use.baseURL);
    try {
      await signInAdmin(admin.page);
      await admin.page.keyboard.press("Control+k");
      const search = admin.page.getByRole("combobox", { name: "Search" });
      await search.pressSequentially("certificate");
      const tickets = admin.page.getByRole("group", { name: "Support tickets" });
      await expect(tickets.getByRole("option", { name: /I cannot see my certificate/ })).toBeVisible();
      await admin.page.keyboard.press("ArrowDown");
      await admin.page.keyboard.press("Enter");
      await expect(admin.page).toHaveURL(/\/admin\/(support|search)/);
    } finally {
      await admin.close();
    }
  });
});
