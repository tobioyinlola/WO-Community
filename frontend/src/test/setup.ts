import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

declare global {
  interface Window {
    /** Tests set this to pretend the operating system prefers a dark theme. */
    __systemDark?: boolean;
  }
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.__systemDark = false;
  document.documentElement.removeAttribute("data-theme");
});

// jsdom has no matchMedia; the theme provider reads it.
vi.stubGlobal("matchMedia", (query: string) => ({
  matches: query.includes("dark") ? Boolean(window.__systemDark) : false,
  media: query,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  addListener: () => undefined,
  removeListener: () => undefined,
  dispatchEvent: () => false,
  onchange: null,
}));
