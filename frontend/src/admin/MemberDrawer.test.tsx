import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemberDrawer } from "./MemberDrawer";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  const { default: createClient } = await import("openapi-fetch");
  return { ...actual, api: createClient({ baseUrl: "http://localhost", fetch: actual.authFetch }) };
});
vi.mock("../auth/AuthProvider", () => ({ useAuth: () => ({ me: { roles: ["super_admin"] } }) }));
vi.mock("../ui/Toast", () => ({ useToast: () => ({ show: () => undefined }) }));
vi.mock("../api/reference", () => ({ useCountries: () => ({ data: [{ value: "NG", label: "Nigeria" }] }) }));

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.restoreAllMocks());

const member = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "ada@example.com",
  name: "Ada Okafor",
  status: "pending",
  roles: [],
  email_verified_at: null,
  approved_at: null,
  approval_source: "",
  status_reason: "",
  status_changed_at: null,
  last_login: null,
  created_at: "2026-10-01T10:00:00Z",
  profile: { full_name: "Ada Okafor", headline: "", bio: "", country: "NG", city: "Lagos", website_url: "", linkedin_url: "", x_url: "", skills: [], open_to: [], completeness: 40, startup_name: "Acme", industry: "Fintech", stage: "Seed", pitch: "" },
  account: { invited_by: null, referred_by: null, approved_by: null },
  activity: { posts: 2, comments: 3, events_attended: 1, jobs_posted: 0 },
  learning: { courses_started: 1, courses_completed: 0, certificates: [] },
  mentorship: null,
  open_tickets: [],
  audit: [],
};

function open() {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(member), { status: 200, headers: { "Content-Type": "application/json" } })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MemberDrawer memberId={member.id} onClose={() => undefined} onAct={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MemberDrawer", () => {
  it("shows the member's sections and the actions that fit a pending, unconfirmed account", async () => {
    open();
    expect(await screen.findByRole("heading", { name: "Ada Okafor" })).toBeInTheDocument();
    for (const name of ["Profile", "Account", "Activity", "Learning", "Mentorship", "Support", "Audit"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Lagos, Nigeria")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suspend" })).not.toBeInTheDocument();
    expect(screen.getByText("Not a mentor.")).toBeInTheDocument();
  });
});
