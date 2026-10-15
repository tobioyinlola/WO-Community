import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { MENTOR, signIn, signInAdmin } from "./helpers";

/**
 * Takes the review screenshots under docs/changes/screenshots: every new screen in light and dark at
 * 1440, 1024 and 390 pixels. It writes files, so it only runs when asked:
 *
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts
 *
 * Each screen is opened once per theme and then resized, so the three widths show the same state.
 */
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to take the review screenshots");
test.describe.configure({ mode: "serial" });
test.setTimeout(30 * 60_000);

// Playwright runs from the frontend folder.
const OUT = path.resolve(process.cwd(), "../docs/changes/screenshots");
const WIDTHS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1024", width: 1024, height: 768 },
  { name: "390", width: 390, height: 844 },
] as const;
const THEMES = ["light", "dark"] as const;

type Scene = { name: string; open: (page: Page) => Promise<void>; full?: boolean };

async function settle(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(500);
}

async function theme(page: Page, value: (typeof THEMES)[number]) {
  if (page.url() === "about:blank") await page.goto("/");
  await page.evaluate((v) => window.localStorage.setItem("wo-theme", v), value);
}

async function shoot(page: Page, scene: Scene, mode: (typeof THEMES)[number]) {
  await page.setViewportSize({ width: 1440, height: 900 });
  await scene.open(page);
  await settle(page);
  for (const size of WIDTHS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.waitForTimeout(350);
    await page.screenshot({
      path: path.join(OUT, `${scene.name}-${mode}-${size.name}.jpg`),
      type: "jpeg",
      quality: 82,
      fullPage: scene.full !== false,
    });
  }
}

async function capture(context: BrowserContext, page: Page, scenes: Scene[]) {
  for (const mode of THEMES) {
    await theme(page, mode);
    for (const scene of scenes) await shoot(page, scene, mode);
  }
  await context.close();
}

async function fresh(browser: Browser, baseURL: string | undefined) {
  const context = await browser.newContext({ baseURL, reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
  return { context, page: await context.newPage() };
}

const open = (url: string) => async (page: Page) => {
  await page.goto(url);
};

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

test("member screens", async ({ browser }, info) => {
  const { context, page } = await fresh(browser, info.project.use.baseURL);
  await signIn(page);
  const scenes: Scene[] = [
    { name: "member-home", open: open("/app") },
    {
      name: "support-drawer",
      full: false,
      open: async (p) => {
        await p.goto("/app");
        await p.getByRole("button", { name: "Contact support" }).first().click();
        await expect(p.getByRole("dialog")).toBeVisible();
      },
    },
    { name: "support-requests", open: open("/app/support") },
    {
      name: "support-ticket",
      open: async (p) => {
        await p.goto("/app/support");
        await p.getByRole("link", { name: /SUP-\d+/ }).first().click();
        await expect(p.getByRole("heading", { level: 1 })).toBeVisible();
      },
    },
    {
      name: "search-popover",
      full: false,
      open: async (p) => {
        await p.goto("/app");
        await p.getByRole("combobox", { name: "Search" }).fill("ada");
        await expect(p.getByRole("listbox")).toBeVisible();
      },
    },
    { name: "search-results", open: open("/app/search?q=ada") },
    {
      name: "bell-popover",
      full: false,
      open: async (p) => {
        await p.goto("/app");
        await p.getByRole("button", { name: /^Notifications/ }).click();
        await expect(p.getByRole("dialog", { name: /Notifications/ })).toBeVisible();
      },
    },
    { name: "notifications", open: open("/app/notifications") },
    { name: "learn-catalogue", open: open("/app/learn") },
    {
      name: "course-free",
      open: async (p) => {
        await p.goto("/app/learn");
        await p.getByRole("link", { name: /Customer discovery for founders/ }).first().click();
        await expect(p.getByRole("heading", { level: 1 })).toBeVisible();
      },
    },
    {
      name: "course-paid",
      open: async (p) => {
        await p.goto("/app/learn");
        await p.getByRole("link", { name: /Financial models investors trust/ }).first().click();
        await expect(p.getByRole("heading", { level: 1 })).toBeVisible();
      },
    },
    {
      name: "player",
      open: async (p) => {
        await p.goto("/app/learn/my");
        await p.getByRole("link", { name: /Fundraising for African startups/ }).first().click();
        await p.getByRole("link", { name: /Review the course|Continue learning|Start learning/ }).first().click();
        await expect(p.getByRole("heading", { level: 1 })).toBeVisible();
      },
    },
    { name: "my-learning", open: open("/app/learn/my") },
    { name: "certificates", open: open("/app/learn/certificates") },
    {
      name: "certificate",
      open: async (p) => {
        await p.goto("/app/learn/certificates");
        await p.getByRole("link", { name: "View" }).first().click();
        await expect(p.getByRole("figure")).toBeVisible();
      },
    },
    {
      name: "mentor-booking",
      open: async (p) => {
        await p.goto("/app/mentors");
        await p.getByRole("link", { name: /Ada Nwosu/ }).first().click();
        await expect(p.getByRole("group", { name: "Days with times" })).toBeVisible();
      },
    },
    {
      name: "mentor-request-dialog",
      full: false,
      open: async (p) => {
        await p.goto("/app/mentors");
        await p.getByRole("link", { name: /Ada Nwosu/ }).first().click();
        await p.getByRole("group", { name: /Times on/ }).first().getByRole("button").first().click();
        await expect(p.getByRole("dialog", { name: "Request this session" })).toBeVisible();
      },
    },
    { name: "settings", open: open("/app/settings") },
  ];
  await capture(context, page, scenes);
});

test("mentor settings", async ({ browser }, info) => {
  const { context, page } = await fresh(browser, info.project.use.baseURL);
  await signIn(page, MENTOR);
  const scenes: Scene[] = [
    { name: "mentor-settings", open: open("/app/settings/mentorship") },
    {
      name: "mentor-preview",
      full: false,
      open: async (p) => {
        await p.goto("/app/settings/mentorship");
        await p.getByRole("button", { name: "Preview as mentee" }).click();
        await expect(p.getByRole("dialog", { name: "As a mentee sees it" })).toBeVisible();
      },
    },
  ];
  await capture(context, page, scenes);
});

test("public screens", async ({ browser }, info) => {
  const member = await fresh(browser, info.project.use.baseURL);
  await signIn(member.page);
  await member.page.goto("/app/learn/certificates");
  const text = (await member.page.getByRole("listitem").filter({ hasText: "Fundraising for African startups" }).first().textContent()) ?? "";
  const number = text.match(/WO-C-\d{4}-\d{6}/)?.[0] ?? "WO-C-2026-000001";
  await member.context.close();

  const { context, page } = await fresh(browser, info.project.use.baseURL);
  const scenes: Scene[] = [
    { name: "verify-certificate", open: open(`/verify/${number}`) },
    { name: "verify-unknown", open: open("/verify/WO-C-2026-999999") },
    { name: "help", open: open("/help") },
    {
      name: "register-referral",
      open: async (p) => {
        await p.goto("/register");
        await p.getByLabel("Email").fill("preview@demo.test");
        await p.getByLabel("Password", { exact: true }).fill("a-long-passphrase-2026");
        await p.getByRole("button", { name: "Continue" }).click();
        await p.getByLabel("Full name").fill("Preview Person");
        await p.getByLabel("Country").selectOption({ label: "Nigeria" });
        await p.getByLabel("City").fill("Lagos");
        await p.getByLabel("LinkedIn profile").fill("linkedin.com/in/new-member");
        await p.getByRole("button", { name: "Continue" }).click();
        await p.getByLabel("Company name").fill("Preview Labs");
        await p.getByLabel("Company website").fill("newcompany.example.com");
        await p.getByLabel("Sector").selectOption({ label: "Fintech" });
        await p.getByLabel("Stage").selectOption({ index: 1 });
        await p.getByLabel("What does it do?").fill("Payments for small shops.");
        await p.getByRole("button", { name: "Continue" }).click();
        const group = p.getByRole("group", { name: "Who referred you?" });
        await group.getByLabel("How did you hear about us?").selectOption({ label: "A WO Community member" });
        await group.getByLabel("Search for them").fill("Amaka");
        await group.getByRole("button", { name: /Amaka Obi/ }).click();
      },
    },
  ];
  await capture(context, page, scenes);
});

test("admin screens", async ({ browser }, info) => {
  const { context, page } = await fresh(browser, info.project.use.baseURL);
  await signInAdmin(page);
  const scenes: Scene[] = [
    { name: "admin-dashboard", open: open("/admin") },
    { name: "admin-members", open: open("/admin/members") },
    { name: "admin-support-inbox", open: open("/admin/support") },
    {
      name: "admin-support-ticket",
      full: false,
      open: async (p) => {
        await p.goto("/admin/support");
        await p.getByRole("row").filter({ hasText: /SUP-\d+/ }).first().click();
        await expect(p.getByRole("dialog")).toBeVisible();
      },
    },
    { name: "admin-canned-replies", open: open("/admin/support/replies") },
    { name: "admin-courses", open: open("/admin/courses") },
    {
      name: "admin-add-course",
      full: false,
      open: async (p) => {
        await p.goto("/admin/courses");
        await p.getByRole("button", { name: "Add course" }).first().click();
        await expect(p.getByRole("dialog", { name: "Add course" })).toBeVisible();
      },
    },
    {
      name: "admin-course-manage",
      open: async (p) => {
        await p.goto("/admin/courses");
        await p.getByRole("link", { name: "Financial models investors trust" }).first().click();
        await expect(p.getByRole("heading", { level: 1 })).toBeVisible();
      },
    },
    {
      name: "admin-course-draft",
      open: async (p) => {
        await p.goto("/admin/courses");
        await p.getByRole("link", { name: "Hiring your first ten people" }).first().click();
        await expect(p.getByText("Before this can be published")).toBeVisible();
      },
    },
    { name: "admin-course-requests", open: open("/admin/course-requests") },
    { name: "admin-certificates", open: open("/admin/certificates") },
    { name: "admin-certificate-template", open: open("/admin/learning/certificate-template") },
    { name: "admin-approvals", open: open("/admin/approvals") },
    { name: "admin-search", open: open("/admin/search?q=certificate") },
    { name: "admin-design", open: open("/admin/design") },
  ];
  await capture(context, page, scenes);
});
