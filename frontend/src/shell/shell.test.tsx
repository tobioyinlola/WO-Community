import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { GlobalSearch } from "./GlobalSearch";
import { NotificationBell } from "./NotificationBell";
import { highlightParts, matchLinks, MEMBER_LINKS } from "./searchModel";

// The client builds real Request objects, which need an absolute address in this environment.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  const { default: createClient } = await import("openapi-fetch");
  return { ...actual, api: createClient({ baseUrl: "http://localhost", fetch: actual.authFetch }) };
});

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = () => undefined;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => undefined;
});

type Handler = (url: URL, init: Request) => unknown;
let calls: Array<{ method: string; path: string; search: string; body: string }> = [];

/** Answers each API path from a table; anything else is a 404 so a missing stub shows up. */
function stubApi(routes: Record<string, Handler>) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | string) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      const body = request.method === "GET" ? "" : await request.clone().text();
      calls.push({ method: request.method, path: url.pathname, search: url.search, body });
      const handler = routes[`${request.method} ${url.pathname}`];
      if (!handler) return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
      return new Response(JSON.stringify(handler(url, request)), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderWith(ui: React.ReactNode, start = "/app") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[start]}>
        {ui}
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.useRealTimers());
afterEach(() => vi.unstubAllGlobals());

describe("search helpers", () => {
  it("marks every typed word, ignoring case", () => {
    expect(highlightParts("Adaeze Okafor", "okaf ada")).toEqual([
      { text: "Ada", match: true },
      { text: "eze ", match: false },
      { text: "Okaf", match: true },
      { text: "or", match: false },
    ]);
    expect(highlightParts("Nothing here", "zz")).toEqual([{ text: "Nothing here", match: false }]);
    expect(highlightParts("a", "")).toEqual([{ text: "a", match: false }]);
  });

  it("does not treat typed punctuation as a pattern", () => {
    expect(() => highlightParts("C++ (basics)", "c++ (b")).not.toThrow();
  });

  it("matches pages by name or keyword and offers the first few when nothing is typed", () => {
    expect(matchLinks(MEMBER_LINKS, "password", 4).map((l) => l.label)).toEqual(["Settings"]);
    expect(matchLinks(MEMBER_LINKS, "", 3)).toHaveLength(3);
    expect(matchLinks(MEMBER_LINKS, "zzzz", 4)).toEqual([]);
  });
});

const MEMBER_RESULTS = {
  members: [{ type: "member", id: "u1", slug: "ada", title: "Adaeze Okafor", subtitle: "Fintech founder", image: null }],
  startups: [],
  courses: [{ type: "course", id: "c1", slug: "adaptive", title: "Adaptive selling", subtitle: "Someone", image: null }],
};

function SearchHarness() {
  return (
    <>
      <button type="button">Elsewhere</button>
      <textarea aria-label="Notes" />
      <GlobalSearch scope="member" links={MEMBER_LINKS} resultsPath="/app/search" placeholder="Search members" />
    </>
  );
}

describe("GlobalSearch", () => {
  const routes = {
    "GET /api/v1/search": () => MEMBER_RESULTS,
    "GET /api/v1/search/recents": () => ({ terms: ["fintech"] }),
    "POST /api/v1/search/recents": () => ({ terms: ["ada"] }),
    "DELETE /api/v1/search/recents": () => undefined,
  };

  it("the slash key focuses the field, but not while typing somewhere else", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    const field = screen.getByRole("combobox");
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    await user.keyboard("/");
    expect(field).toHaveFocus();
    await user.click(screen.getByLabelText("Notes"));
    await user.keyboard("a/b");
    expect(screen.getByLabelText("Notes")).toHaveValue("a/b");
    expect(field).not.toHaveFocus();
  });

  it("Ctrl K reaches the field too, and Esc closes and gives focus back", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
    await user.click(elsewhere);
    await user.keyboard("{Control>}k{/Control}");
    const field = screen.getByRole("combobox");
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(field).toHaveAttribute("aria-expanded", "false");
    expect(elsewhere).toHaveFocus();
  });

  it("offers recent searches and suggested pages before anything is typed", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByRole("option", { name: "fintech" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Settings/ })).toBeInTheDocument();
  });

  it("lists results in groups with the match marked, after two letters", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "ada");
    const members = await screen.findByRole("group", { name: "Members" });
    expect(within(members).getByRole("option", { name: /Adaeze Okafor/ })).toBeInTheDocument();
    expect(members.querySelector("mark")?.textContent).toBe("Ada");
    expect(screen.getByRole("group", { name: "Courses" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Startups" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /See all results for/ })).toBeInTheDocument();
    const asked = calls.find((c) => c.path === "/api/v1/search");
    expect(asked?.search).toContain("q=ada");
  });

  it("does not search for a single letter", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "a");
    await new Promise((r) => setTimeout(r, 350));
    expect(calls.some((c) => c.path === "/api/v1/search")).toBe(false);
  });

  it("arrow keys and Enter open a result, and the term is remembered", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "ada");
    await screen.findByRole("group", { name: "Members" });
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /Adaeze Okafor/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("where")).toHaveTextContent("/app/members/u1");
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.body.includes('"term":"ada"'))).toBe(true));
  });

  it("Enter with nothing highlighted opens the full results page", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "ada");
    await screen.findByRole("group", { name: "Members" });
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("where")).toHaveTextContent("/app/search?q=ada");
  });

  it("Tab jumps to the next group", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "ada");
    await screen.findByRole("group", { name: "Members" });
    await user.keyboard("{ArrowDown}{Tab}");
    expect(screen.getByRole("option", { name: /Adaptive selling/ })).toHaveAttribute("aria-selected", "true");
  });

  it("says so when nothing matches", async () => {
    stubApi({ ...routes, "GET /api/v1/search": () => ({}) });
    const user = userEvent.setup();
    renderWith(<SearchHarness />);
    await user.type(screen.getByRole("combobox"), "qqqq");
    expect(await screen.findByText(/No results for/)).toBeInTheDocument();
  });
});

function item(id: string, title: string, read = false) {
  return { id, type: "session_requested", title, link: "/app/mentors/sessions", meta: {}, read, created_at: new Date().toISOString() };
}

describe("NotificationBell", () => {
  it("shows the unread count, and 9+ above nine", async () => {
    stubApi({ "GET /api/v1/notifications/unread-count": () => ({ unread_count: 12 }) });
    renderWith(<NotificationBell />);
    expect(await screen.findByRole("button", { name: "Notifications, 12 unread" })).toBeInTheDocument();
    expect(screen.getByText("9+")).toBeInTheDocument();
  });

  it("shows no badge at zero", async () => {
    stubApi({ "GET /api/v1/notifications/unread-count": () => ({ unread_count: 0 }) });
    renderWith(<NotificationBell />);
    const bell = await screen.findByRole("button", { name: "Notifications" });
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(bell.querySelector(".wo-bell__badge")).toBeNull();
  });

  it("opens a popover with the unread ones, and choosing one marks it read and goes there", async () => {
    stubApi({
      "GET /api/v1/notifications/unread-count": () => ({ unread_count: 2 }),
      "GET /api/v1/notifications": () => ({ results: [item("n1", "Ngozi asked for a session"), item("n2", "A reply")], next_cursor: null, unread_count: 2 }),
      "POST /api/v1/notifications/read": () => ({ updated: 1, unread_count: 1 }),
    });
    const user = userEvent.setup();
    renderWith(<NotificationBell />);
    await user.click(await screen.findByRole("button", { name: /Notifications, 2 unread/ }));
    const list = await screen.findByRole("button", { name: /Ngozi asked for a session/ });
    expect(calls.find((c) => c.path === "/api/v1/notifications")?.search).toContain("unread=true");
    await user.click(list);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.body.includes("n1"))).toBe(true));
    expect(screen.getByTestId("where")).toHaveTextContent("/app/mentors/sessions");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says you are all caught up when nothing is unread, and links to the full page", async () => {
    stubApi({
      "GET /api/v1/notifications/unread-count": () => ({ unread_count: 0 }),
      "GET /api/v1/notifications": () => ({ results: [], next_cursor: null, unread_count: 0 }),
    });
    const user = userEvent.setup();
    renderWith(<NotificationBell />);
    await user.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(await screen.findByText("You're all caught up")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all notifications" })).toHaveAttribute("href", "/app/notifications");
  });

  it("marks everything read from the header", async () => {
    stubApi({
      "GET /api/v1/notifications/unread-count": () => ({ unread_count: 1 }),
      "GET /api/v1/notifications": () => ({ results: [item("n1", "One")], next_cursor: null, unread_count: 1 }),
      "POST /api/v1/notifications/read": () => ({ updated: 1, unread_count: 0 }),
    });
    const user = userEvent.setup();
    renderWith(<NotificationBell />);
    await user.click(await screen.findByRole("button", { name: /Notifications, 1 unread/ }));
    await user.click(await screen.findByRole("button", { name: "Mark all as read" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.body.includes('"all":true'))).toBe(true));
  });

  it("renders nothing for an account that has no notification centre", () => {
    stubApi({});
    renderWith(<NotificationBell enabled={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });
});
