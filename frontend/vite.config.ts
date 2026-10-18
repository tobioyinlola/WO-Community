import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  // A production build that does not know where the API is would call the front end's own host and
  // get the page back instead of data, so the build stops here rather than ship that.
  if (command === "build" && mode === "production") {
    const url = env.VITE_API_URL ?? "";
    if (!/^https:\/\/[^/]+\.[^/]+/.test(url) || url.includes("localhost")) {
      throw new Error(`VITE_API_URL must be the public https address of the API (for example https://api.example.com), got "${url}".`);
    }
  }
  return {
    plugins: [react()],
    server: {
      // Development only: the API runs separately, so forward its paths and the browser sees one origin.
      // /s/ is a shared link: the API serves its preview page, as the hosting does in production.
      proxy: { "/api": env.VITE_DEV_API_PROXY ?? "http://localhost:8000", "/s/": env.VITE_DEV_API_PROXY ?? "http://localhost:8000" },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      // Browser tests run with Playwright (npm run e2e), not here.
      exclude: ["e2e/**", "node_modules/**"],
    },
  };
});
