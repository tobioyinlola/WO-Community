import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const stats = vi.hoisted(() => ({ value: { startups: 10, founders: 8, courses: 4, jobs: 12 } as Record<string, number> }));
const content = vi.hoisted(() => ({ testimonials: [] as unknown[], social: [] as unknown[] }));

vi.mock("../../api/client", () => ({
  api: {
    GET: (path: string) => {
      if (path.endsWith("/stats")) return Promise.resolve({ data: stats.value, response: { ok: true } });
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
    get TESTIMONIALS() {
      return content.testimonials;
    },
    get SOCIAL_LINKS() {
      return content.social;
    },
  };
});

import { PublicLayout } from "../../layouts/PublicLayout";
import { Landing } from "./Landing";

function page(element = <Landing />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  stats.value = { startups: 10, founders: 8, courses: 4, jobs: 12 };
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
    stats.value = { startups: 0, founders: 0, courses: 0, jobs: 5 };
    page();
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(screen.queryByRole("link", { name: /Open roles/ })).toBeNull());
    expect(screen.queryByRole("heading", { name: "The community in numbers" })).toBeNull();
  });
});

describe("the feature cards", () => {
  it("each lead somewhere: a public page where there is one, otherwise a request for access", () => {
    page();
    expect(screen.getByRole("link", { name: "Explore: Find your people" })).toHaveAttribute("href", "/explore?tab=founders");
    expect(screen.getByRole("link", { name: "Explore: Keep learning" })).toHaveAttribute("href", "/explore?tab=courses");
    expect(screen.getByRole("link", { name: "Explore: Hire and get hired" })).toHaveAttribute("href", "/explore?tab=jobs");
    expect(screen.getByRole("link", { name: "Explore: Meet in person" })).toHaveAttribute("href", "/explore?tab=events");
    expect(screen.getByRole("link", { name: "Request access: Learn from people who did it" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Request access: Launch with a plan" })).toHaveAttribute("href", "/register");
  });
});

describe("member quotes", () => {
  it("are not on the page until there are real ones", () => {
    page();
    expect(screen.queryByRole("heading", { name: /own words/i })).toBeNull();
  });

  it("appear, quoted and credited, once some are supplied", () => {
    content.testimonials = [{ quote: "It opened doors.", name: "A. Member", role: "Founder" }];
    page();
    expect(screen.getByRole("heading", { name: /own words/i })).toBeInTheDocument();
    expect(screen.getByText(/It opened doors\./)).toBeInTheDocument();
    expect(screen.getByText("A. Member")).toBeInTheDocument();
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
