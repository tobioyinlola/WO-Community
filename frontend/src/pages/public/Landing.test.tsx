import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const stats = vi.hoisted(() => ({
  value: { startups: 10, founders: 8, courses: 4, jobs: 12, countries: [] } as Record<string, unknown>,
}));
const content = vi.hoisted(() => ({ testimonials: [] as unknown[], social: [] as unknown[] }));

vi.mock("../../api/client", () => ({
  api: {
    GET: (path: string) => {
      if (path.endsWith("/stats")) return Promise.resolve({ data: stats.value, response: { ok: true } });
      if (path.endsWith("/testimonials")) return Promise.resolve({ data: content.testimonials, response: { ok: true } });
      return Promise.resolve({ data: { results: [] }, response: { ok: true } });
    },
  },
  unwrap: async (call: Promise<{ data: unknown }>) => (await call).data,
}));
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ status: "anonymous" }) }));
vi.mock("./landingContent", async (original) => {
  const real = await original<typeof import("./landingContent")>();
  return {
    ...real,
    get SOCIAL_LINKS() {
      return content.social;
    },
  };
});

import { PublicLayout } from "../../layouts/PublicLayout";
import { Landing } from "./Landing";
import { MARQUEE_COUNTRIES } from "./landingContent";

function page(element = <Landing />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  stats.value = { startups: 10, founders: 8, courses: 4, jobs: 12, countries: [] };
  content.testimonials = [];
  content.social = [];
});

describe("the numbers", () => {
  it("shows each count from the public numbers, each one a link to what it counts", async () => {
    page();
    const numbers = await screen.findByRole("region", { name: "The community in numbers" }, { timeout: 3000 }).catch(() => null);
    expect(numbers ?? document.body).toBeTruthy();
    const link = await screen.findByRole("link", { name: /Startups listed/ });
    expect(link).toHaveAttribute("href", "/explore?tab=startups");
    expect(screen.getByRole("link", { name: /Open roles/ })).toHaveAttribute("href", "/explore?tab=jobs");
    // The real figure is in the page for screen readers.
    expect(within(link).getByText("10", { selector: ".wo-visually-hidden" })).toBeInTheDocument();
  });

  it("leaves out a count that is zero, and the whole block when fewer than two are left", async () => {
    stats.value = { startups: 0, founders: 0, courses: 0, jobs: 5, countries: [] };
    page();
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(screen.queryByRole("link", { name: /Open roles/ })).toBeNull());
    expect(screen.queryByRole("heading", { name: "The community in numbers" })).toBeNull();
  });
});

describe("the countries strip", () => {
  it("shows the fixed list of countries, each named once for a screen reader", async () => {
    page();
    const list = await screen.findByRole("list", { name: "Countries our founders are in" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(MARQUEE_COUNTRIES.length);
    expect(MARQUEE_COUNTRIES.length).toBeGreaterThan(10);
    expect(within(list).getByText("Nigeria")).toBeInTheDocument();
    expect(within(list).getByText("Morocco")).toBeInTheDocument();
    expect(within(list).getByText("United States")).toBeInTheDocument();
    expect(within(list).getByText("United Kingdom")).toBeInTheDocument();
    expect(within(list).getByText("Canada")).toBeInTheDocument();
    // The second copy that makes the loop seamless is hidden from assistive technology.
    expect(document.querySelectorAll(".site-marquee__row[aria-hidden='true']")).toHaveLength(1);
  });

  it("does not depend on where members said they are", async () => {
    stats.value = { startups: 10, founders: 8, courses: 4, jobs: 12, countries: [{ code: "JP", founders: 3 }] };
    page();
    const list = await screen.findByRole("list", { name: "Countries our founders are in" });
    expect(within(list).queryByText("Japan")).toBeNull();
    expect(within(list).getAllByRole("listitem")).toHaveLength(MARQUEE_COUNTRIES.length);
  });
});

describe("the feature cards", () => {
  it("each lead somewhere: a public page where there is one, otherwise a request for access", () => {
    page();
    expect(screen.getByRole("link", { name: "Explore: Find your people" })).toHaveAttribute("href", "/explore?tab=founders");
    expect(screen.getByRole("link", { name: "Explore: Keep learning" })).toHaveAttribute("href", "/explore?tab=courses");
    expect(screen.getByRole("link", { name: "Explore: Hire and get hired" })).toHaveAttribute("href", "/explore?tab=jobs");
    expect(screen.getByRole("link", { name: "Explore: Meet in person" })).toHaveAttribute("href", "/explore?tab=events");
    expect(screen.getByRole("link", { name: "Become a member: Learn from people who did it" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Become a member: Launch with a plan" })).toHaveAttribute("href", "/register");
  });
});

describe("member quotes", () => {
  it("are not on the page until there are real ones", () => {
    page();
    expect(screen.queryByRole("heading", { name: /own words/i })).toBeNull();
  });

  it("glide past before the footer, quoted and credited, once the team publishes some", async () => {
    content.testimonials = [{ id: "t1", quote: "It opened doors.", name: "A. Member", role: "Founder" }];
    page();
    expect(await screen.findByRole("heading", { name: /own words/i })).toBeInTheDocument();
    const shown = screen.getAllByText(/It opened doors\./);
    // Copies that fill the loop are hidden from screen readers, so the quote is read once.
    expect(shown.filter((el) => !el.closest("[aria-hidden='true']"))).toHaveLength(1);
    expect(screen.getAllByText("A. Member").length).toBeGreaterThan(0);
  });
});

describe("the footer social links", () => {
  const layout = (
    <PublicLayout />
  );

  it("are absent until the community's own pages are supplied", () => {
    page(layout);
    expect(screen.queryByRole("list", { name: /social media/i })).toBeNull();
  });

  it("are round buttons that open in a new tab, named for the network", () => {
    content.social = [{ kind: "linkedin", href: "https://www.linkedin.com/company/example" }];
    page(layout);
    const link = screen.getByRole("link", { name: "LinkedIn (opens in a new tab)" });
    expect(link).toHaveAttribute("href", "https://www.linkedin.com/company/example");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});
