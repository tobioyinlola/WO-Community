/** Lists the contrast pairings axe could not decide, for both themes, so they can be checked by hand. */
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "@playwright/test";

const base = process.env.BASE_URL ?? "http://localhost:5173";
const browser = await chromium.launch({ channel: process.env.BROWSER ?? "msedge" });
for (const theme of ["light", "dark"]) {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < h; y += 350) { await page.evaluate((t) => window.scrollTo(0, t), y); await page.waitForTimeout(80); }
  await page.waitForTimeout(900);
  await page.evaluate(() => window.scrollTo(0, 0));
  const r = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
  console.log(theme, "violations:", r.violations.length, "passes:", r.passes.flatMap((p) => p.nodes).length, "undecided:", r.incomplete.flatMap((i) => i.nodes).length);
  for (const n of r.incomplete.flatMap((i) => i.nodes)) console.log("  undecided:", n.target.join(" "), "-", n.any[0]?.message?.slice(0, 90));
}
await browser.close();
