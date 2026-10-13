/**
 * Captures the public landing page for a design review.
 *
 *   node tools/landing-capture.mjs before   (or: after)
 *
 * Writes full page screenshots at 360, 768 and 1440 px in the light and dark themes to
 * docs/changes/landing-screenshots/, and the page's structure (sections, headings, links, copy) to
 * docs/changes/landing-screenshots/<label>-structure.json so two runs can be compared.
 * Needs the front end (and the API, for events and news) running; BASE_URL defaults to
 * http://localhost:5173 and BROWSER to msedge.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const label = process.argv[2] ?? "after";
const base = process.env.BASE_URL ?? "http://localhost:5173";
const out = new URL("../../docs/changes/landing-screenshots/", import.meta.url);
await mkdir(out, { recursive: true });

const browser = await chromium.launch({ channel: process.env.BROWSER ?? "msedge" });
const structure = {};

for (const width of [360, 768, 1440]) {
  for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({
      viewport: { width, height: width === 1440 ? 900 : 800 },
      timezoneId: "Africa/Lagos",
      locale: "en-GB",
    });
    const page = await context.newPage();
    await page.goto(base + "/", { waitUntil: "networkidle" });
    // The app is light only; the dark tokens are applied directly so the dark styles can be checked.
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    // Scroll down in steps so anything revealed on scroll is shown before the picture is taken.
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; y < height; y += 400) {
      await page.evaluate((top) => window.scrollTo(0, top), y);
      await page.waitForTimeout(120);
    }
    await page.waitForTimeout(1400); // count ups and line drawings finish
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await page.screenshot({ path: fileURLToPath(new URL(`${label}-${width}-${theme}.png`, out)), fullPage: true });
    if (width === 1440 && theme === "light") {
      structure.page = await page.evaluate(() => {
        const text = (el) => (el.textContent ?? "").replace(/\s+/g, " ").trim();
        const area = (root) => ({
          headings: [...root.querySelectorAll("h1,h2,h3,h4")].map((h) => `${h.tagName} ${text(h)}`),
          links: [...root.querySelectorAll("a")].map((a) => `${text(a) || a.getAttribute("aria-label")} -> ${a.getAttribute("href")}`),
          buttons: [...root.querySelectorAll("button")].map((b) => text(b) || b.getAttribute("aria-label")),
          paragraphs: [...root.querySelectorAll("p,li")].map(text).filter(Boolean),
        });
        return {
          title: document.title,
          nav: area(document.querySelector("nav")),
          main: area(document.querySelector("main")),
          sections: [...document.querySelectorAll("main > section")].map((s) => s.getAttribute("aria-labelledby") ?? s.getAttribute("aria-label") ?? s.className),
          footer: area(document.querySelector("footer")),
        };
      });
    }
    await context.close();
  }
}
await browser.close();
await writeFile(new URL(`${label}-structure.json`, out), JSON.stringify(structure, null, 2));
console.log("captured", label);
