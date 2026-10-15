import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { components } from "../api/schema";
import { ApprovalDrawer } from "./ApprovalDrawer";
import { BarChart, niceMax, type DayPoint } from "./kit/BarChart";
import { DataTable, type Sort } from "./kit/DataTable";
import { changeBetween, Delta } from "./kit/Delta";
import { permissionsFor } from "./permissions";
import { visibleNav } from "./shell/nav";
import { Sidebar } from "./shell/Sidebar";

// The client builds real Request objects, which need an absolute address in this environment.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  const { default: createClient } = await import("openapi-fetch");
  return { ...actual, api: createClient({ baseUrl: "http://localhost", fetch: actual.authFetch }) };
});

// jsdom lacks a few browser features that the menus and the palette lean on.
beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = () => undefined;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => undefined;
});
afterEach(() => vi.restoreAllMocks());

const ADMIN = permissionsFor(["super_admin"]);

describe("Sidebar", () => {
  const entries = visibleNav(ADMIN);
  const person = { name: "Admin", role: "super_admin" };

  function Harness({ start = "/admin/approvals", collapsed = false, onToggle = () => undefined }: { start?: string; collapsed?: boolean; onToggle?: () => void }) {
    return (
      <MemoryRouter initialEntries={[start]}>
        <Sidebar entries={entries} counts={{ registrations_awaiting_approval: 3 }} collapsed={collapsed} onToggle={onToggle} onHelp={() => undefined} person={person} />
      </MemoryRouter>
    );
  }

  it("marks the page being shown and opens the group that holds it", () => {
    render(<Harness />);
    expect(screen.getByRole("link", { name: /Approvals/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /Members/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /Content/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("shows how many requests are waiting, in words for a screen reader", () => {
    render(<Harness />);
    expect(screen.getByLabelText("3 waiting")).toBeInTheDocument();
  });

  it("opens and closes a group with the keyboard", async () => {
    const user = userEvent.setup();
    render(<Harness start="/admin" />);
    const jobs = screen.getByRole("button", { name: /^Jobs/ });
    expect(jobs).toHaveAttribute("aria-expanded", "false");
    jobs.focus();
    await user.keyboard("{Enter}");
    expect(jobs).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: /All jobs/ })).toBeVisible();
    await user.keyboard(" ");
    expect(jobs).toHaveAttribute("aria-expanded", "false");
  });

  it("asks to be collapsed from its own button", async () => {
    const onToggle = vi.fn();
    render(<Harness onToggle={onToggle} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("keeps every link reachable by name when it is a rail of icons", () => {
    render(<Harness collapsed />);
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.queryByText("All members")).not.toBeInTheDocument();
  });

  it("lists a group's pages in a flyout from the rail", async () => {
    render(<Harness collapsed start="/admin" />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Members" }));
    expect(await screen.findByRole("menuitem", { name: /Approvals/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /All members/ })).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  interface Row { id: string; name: string; score: number }
  const rows: Row[] = [{ id: "1", name: "Amaka", score: 80 }, { id: "2", name: "Tunde", score: 40 }];
  const columns: Array<ColumnDef<Row, unknown>> = [
    { id: "name", header: "Name", meta: { sortKey: "name" }, cell: ({ row }) => row.original.name },
    { id: "score", header: "Score", meta: { align: "end" as const }, cell: ({ row }) => row.original.score },
  ];

  function Table({ onSort = () => undefined, onOpen, sort }: { onSort?: (s: Sort) => void; onOpen?: (r: Row) => void; sort?: Sort }) {
    const [picked, setPicked] = useState<Set<string>>(new Set());
    return (
      <>
        <DataTable caption="People" columns={columns} data={rows} getRowId={(r) => r.id} rowLabel={(r) => r.name} selected={picked} onSelectedChange={setPicked} sort={sort} onSortChange={onSort} onRowClick={onOpen} />
        <p data-testid="count">{picked.size}</p>
      </>
    );
  }

  it("reports a sort in the direction that was asked for", async () => {
    const onSort = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Table onSort={onSort} />);
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(onSort).toHaveBeenLastCalledWith({ id: "name", desc: false });
    rerender(<Table onSort={onSort} sort={{ id: "name", desc: false }} />);
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending");
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(onSort).toHaveBeenLastCalledWith({ id: "name", desc: true });
  });

  it("does not offer to sort a column the server cannot sort", () => {
    render(<Table />);
    expect(screen.queryByRole("button", { name: "Score" })).not.toBeInTheDocument();
  });

  it("selects one row, every row, and none, with labelled tick boxes", async () => {
    const user = userEvent.setup();
    render(<Table />);
    await user.click(screen.getByRole("checkbox", { name: "Select Amaka" }));
    expect(screen.getByTestId("count")).toHaveTextContent("1");
    await user.click(screen.getByRole("checkbox", { name: "Select every row on this page" }));
    expect(screen.getByTestId("count")).toHaveTextContent("2");
    await user.click(screen.getByRole("checkbox", { name: "Select every row on this page" }));
    expect(screen.getByTestId("count")).toHaveTextContent("0");
  });

  it("opens a row with Enter, and with a click that is not on a control", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<Table onOpen={onOpen} />);
    const first = within(screen.getAllByRole("row")[1] as HTMLElement);
    await user.click(first.getByText("80"));
    expect(onOpen).toHaveBeenCalledWith(rows[0]);
    (screen.getAllByRole("row")[2] as HTMLElement).focus();
    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenLastCalledWith(rows[1]);
  });

  it("shows the empty state instead of an empty table", () => {
    render(<DataTable caption="People" columns={columns} data={[]} getRowId={(r: Row) => r.id} empty={<p>Nobody here</p>} />);
    expect(screen.getByText("Nobody here")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("BarChart", () => {
  const points: DayPoint[] = [
    { label: "1 Oct", current: 4, previous: 2 },
    { label: "2 Oct", current: 8, previous: 6 },
    { label: "3 Oct", current: null, previous: 3 },
  ];

  it("is one focus stop that moves between days with the arrow keys", async () => {
    const user = userEvent.setup();
    render(<BarChart title="Sign ups" points={points} currentLabel="October" previousLabel="Last month" />);
    const chart = screen.getByRole("listbox");
    await user.tab();
    expect(chart).toHaveFocus();
    // It starts on the last day that has happened.
    expect(chart.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[1]?.id);
    await user.keyboard("{ArrowLeft}");
    expect(chart.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[0]?.id);
    await user.keyboard("{End}");
    expect(chart.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[2]?.id);
  });

  it("says the numbers for each day and marks days still to come", () => {
    render(<BarChart title="Sign ups" points={points} currentLabel="October" previousLabel="Last month" />);
    expect(screen.getByRole("option", { name: /1 Oct: 4 october, 2 last month/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /3 Oct: not yet/i })).toBeInTheDocument();
  });

  it("offers the same figures as a table", () => {
    render(<BarChart title="Sign ups" points={points} currentLabel="October" previousLabel="Last month" />);
    const table = screen.getByRole("table", { hidden: true });
    expect(within(table).getByText("1 Oct")).toBeInTheDocument();
  });

  it("rounds the top of the scale to a number the grid reads cleanly", () => {
    expect(niceMax(0)).toBe(4);
    expect(niceMax(7)).toBe(8);
    expect(niceMax(37)).toBe(40);
    expect(niceMax(120)).toBe(120);
  });
});

describe("Delta", () => {
  it("never relies on colour: it carries a sign and words for a screen reader", () => {
    render(<><Delta change={0.12} versus="on yesterday" /><Delta change={-0.5} versus="on yesterday" /></>);
    expect(screen.getByText("+12%")).toBeInTheDocument();
    expect(screen.getByText("−50%")).toBeInTheDocument();
    expect(screen.getByText(/up 12 percent on yesterday/)).toBeInTheDocument();
  });

  it("treats a fall as good news when lower is better", () => {
    const { container } = render(<Delta change={-0.2} versus="on last week" inverse />);
    expect(container.querySelector("[data-tone]")).toHaveAttribute("data-tone", "good");
  });

  it("says there is nothing to compare when the period before was empty", () => {
    expect(changeBetween(5, 0)).toBeNull();
    expect(changeBetween(0, 0)).toBe(0);
    expect(changeBetween(15, 10)).toBe(0.5);
  });
});

describe("ApprovalDrawer", () => {
  const member = {
    id: "01a12d6f-0000-7000-8000-00000000a5e8",
    email: "ife@demo.test",
    status: "pending",
    roles: ["member"],
    email_verified_at: "2026-10-11T08:00:00Z",
    approved_at: "",
    approval_source: "",
    status_reason: "",
    status_changed_at: "",
    last_login: "",
    created_at: "2026-10-11T07:00:00Z",
    name: "Ife Bello",
    country: "NG",
    startup: "Kuda Foods",
    sector: "Agritech",
    stage: "Seed",
  } as components["schemas"]["MemberRow"];

  function json(body: unknown, status = 200) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  function setup(overrides: Partial<React.ComponentProps<typeof ApprovalDrawer>> = {}, linkedin = "https://www.linkedin.com/in/ife-bello") {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: Request) => {
        const url = new URL(input.url, "http://localhost");
        if (url.pathname.endsWith("/application")) {
          return json({
            member,
            profile: { full_name: "Ife Bello", headline: "", country: "NG", city: "Lagos", website_url: "", linkedin_url: linkedin, completeness: 70 },
            startup: { name: "Kuda Foods", country: "NG", city: "Lagos", sector: "Agritech", stage: "Seed", pitch: "Fresh produce in a day.", website_url: "", completeness: 55 },
            timeline: [{ kind: "registered", at: "2026-10-11T07:00:00Z", note: "" }],
            referral: { kind: "member", kind_label: "A WO Community member", detail: "", referrer: { id: "r1", name: "Amaka Obi" }, code_used: "" },
          });
        }
        if (url.pathname.endsWith("/reference/countries")) return json([{ code: "NG", name: "Nigeria" }]);
        return json({}, 404);
      }),
    );
    const props = {
      member,
      position: { index: 1, total: 3 },
      onClose: vi.fn(),
      onPrevious: vi.fn(),
      onNext: vi.fn(),
      onApprove: vi.fn(),
      rejecting: false,
      onRejectingChange: vi.fn(),
      onReject: vi.fn(),
      ...overrides,
    };
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <ApprovalDrawer {...props} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return props;
  }

  it("opens as a dialog with the request, the position and what the person gave", async () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/^Request /)).toBeInTheDocument();
    expect(within(dialog).getByText("2 of 3")).toBeInTheDocument();
    expect(await within(dialog).findByText("Kuda Foods")).toBeInTheDocument();
    expect(await within(dialog).findByText("Nigeria")).toBeInTheDocument();
    expect(within(dialog).getByText("Fresh produce in a day.")).toBeInTheDocument();
  });

  it("shows the LinkedIn profile, and without one asks for it and holds back approval", async () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("link", { name: "linkedin.com/in/ife-bello" })).toHaveAttribute(
      "href",
      "https://www.linkedin.com/in/ife-bello",
    );
    cleanup();
    setup({}, "");
    const missing = screen.getByRole("dialog");
    expect(await within(missing).findByText(/Missing. Needed before approval/)).toBeInTheDocument();
    expect(within(missing).getByLabelText("LinkedIn profile")).toBeInTheDocument();
    expect(within(missing).getByRole("button", { name: "Approve" })).toBeDisabled();
  });

  it("says how they heard of us, with the member who brought them, and offers to edit it", async () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText(/A WO Community member: Amaka Obi/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("keeps focus inside while open and closes on Escape", async () => {
    const props = setup();
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await userEvent.setup().keyboard("{Escape}");
    expect(props.onClose).toHaveBeenCalled();
  });

  it("steps to the previous and next request, and stops at the ends", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: "Next request" }));
    await user.click(screen.getByRole("button", { name: "Previous request" }));
    expect(props.onNext).toHaveBeenCalledOnce();
    expect(props.onPrevious).toHaveBeenCalledOnce();
  });

  it("disables stepping past the first and last request", () => {
    setup({ position: { index: 0, total: 1 } });
    expect(screen.getByRole("button", { name: "Previous request" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next request" })).toBeDisabled();
  });

  it("approves in one press and asks for a reason before rejecting", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(props.onApprove).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(props.onRejectingChange).toHaveBeenCalledWith(true);
  });

  it("will not send a rejection without a reason, and sends the reason typed", async () => {
    const user = userEvent.setup();
    const props = setup({ rejecting: true });
    const reject = screen.getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();
    await user.type(screen.getByLabelText("Why are you rejecting this request?"), "Not a fit");
    expect(reject).toBeEnabled();
    await user.click(reject);
    expect(props.onReject).toHaveBeenCalledWith("Not a fit");
  });
});
