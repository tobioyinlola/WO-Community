import type { ColumnDef } from "@tanstack/react-table";
import { useState, type ReactNode } from "react";
import { Bell, CalendarDays, Search, UserCheck } from "lucide-react";
import { Avatar, Button } from "../components";
import { Drawer } from "../ui/Drawer";
import { PageHeader, useDocumentTitle } from "../ui/blocks";
import { BarChart, type DayPoint } from "./kit/BarChart";
import { changeBetween, Delta } from "./kit/Delta";
import { DataTable, type ColumnMeta } from "./kit/DataTable";
import { KpiCard } from "./kit/KpiCard";
import { Segmented } from "./kit/Segmented";
import { FilterChips, MeterBar, Pager, StatStrip, StatusChip } from "./kit/TableBits";

/** The same content on a light and a dark ground, so both themes can be checked at once. */
function Both({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="adm-design__section" aria-label={title}>
      <h2 className="adm-card__title">{title}</h2>
      <div className="adm-design__pair">
        {(["light", "dark"] as const).map((theme) => (
          <div key={theme} className="adm-frame" data-theme={theme}>
            <p className="adm-frame__label">{theme === "light" ? "Light" : "Dark"}</p>
            {children}
          </div>
        ))}
      </div>
    </section>
  );
}

const DAYS: DayPoint[] = Array.from({ length: 30 }, (_, i) => ({
  label: `${i + 1} Oct`,
  current: i < 18 ? Math.round(6 + 5 * Math.sin(i / 2.2) + (i % 4)) : null,
  previous: Math.round(5 + 4 * Math.cos(i / 3) + (i % 3)),
}));

interface Row {
  id: string;
  name: string;
  status: "Approved" | "Waiting" | "Rejected";
  score: number;
}
const ROWS: Row[] = [
  { id: "1", name: "Amaka Obi", status: "Approved", score: 86 },
  { id: "2", name: "Tunde Kolade", status: "Waiting", score: 52 },
  { id: "3", name: "Zanele Mokoena", status: "Rejected", score: 18 },
];

export default function AdminDesign() {
  useDocumentTitle("Admin design");
  const [tab, setTab] = useState("signups");
  const [selected, setSelected] = useState<Set<string>>(new Set(["2"]));
  const [drawer, setDrawer] = useState(false);
  const [draft, setDraft] = useState("");
  const columns: Array<ColumnDef<Row, unknown>> = [
    {
      id: "name",
      header: "Member",
      meta: { sortKey: "name", label: "Member" } satisfies ColumnMeta,
      cell: ({ row }) => (
        <span className="adm-who">
          <Avatar name={row.original.name} id={row.original.id} size="sm" />
          <span className="adm-who__text"><span className="adm-who__name">{row.original.name}</span><span className="adm-who__id">a5e858c{row.original.id}</span></span>
        </span>
      ),
    },
    { id: "status", header: "Status", cell: ({ row }) => <StatusChip tone={row.original.status === "Approved" ? "success" : row.original.status === "Waiting" ? "warning" : "danger"}>{row.original.status}</StatusChip> },
    { id: "score", header: "Profile", meta: { align: "end" } satisfies ColumnMeta, cell: ({ row }) => <MeterBar value={row.original.score} label={`${row.original.name} profile completeness`} /> },
  ];
  return (
    <>
      <PageHeader eyebrow="Console" title="Admin design" lead="Every console component, in both themes, with sample data. For review only." />

      <Both title="Key figure cards">
        <div className="adm-design__stack">
          <KpiCard highlight label="Pending approvals" tag="Now" value="19" rows={[{ label: "Approved today", value: "4" }, { label: "Approved this month", value: "62" }, { label: "Email not confirmed", value: "7" }]} />
          <KpiCard label="New members" tag="Today" value="12" delta={<Delta change={changeBetween(12, 9)} versus="on yesterday" />} rows={[{ label: "Yesterday", value: "9" }, { label: "This month", value: "148" }, { label: "Last month", value: "131" }]} />
        </div>
      </Both>

      <Both title="Change chips and status">
        <div className="adm-design__stack">
          <p className="adm-design__row">
            <Delta change={0.12} versus="on last month" />
            <Delta change={-0.08} versus="on last month" />
            <Delta change={0} versus="on last month" />
            <Delta change={null} versus="on last month" />
            <Delta change={-0.2} versus="on last month" inverse />
          </p>
          <p className="adm-design__row">
            <StatusChip tone="success">Approved</StatusChip>
            <StatusChip tone="warning">Waiting</StatusChip>
            <StatusChip tone="danger">Suspended</StatusChip>
            <StatusChip tone="info">Scheduled</StatusChip>
            <StatusChip>Draft</StatusChip>
          </p>
          <p className="adm-design__row"><MeterBar value={86} label="High" /><MeterBar value={52} label="Middle" /><MeterBar value={18} label="Low" /></p>
          <p className="adm-design__row"><Button>Primary</Button><Button variant="secondary">Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Danger</Button></p>
        </div>
      </Both>

      <Both title="Segmented control and bar chart">
        <div className="adm-design__stack">
          <Segmented label="Measure" idPrefix="design" controls={false} value={tab} onChange={setTab} options={[{ value: "signups", label: "Sign ups" }, { value: "approvals", label: "Approvals" }, { value: "posts", label: "Posts" }]} />
          <BarChart title="Sign ups" points={DAYS} currentLabel="October" previousLabel="Last month" />
        </div>
      </Both>

      <Both title="Filters, summary and table">
        <div className="adm-design__stack">
          <FilterChips chips={[{ id: "a", label: "Status: Waiting", onRemove: () => undefined }, { id: "b", label: "Role: Mentor", onRemove: () => undefined }]} onClear={() => undefined} />
          <StatStrip columns={3} items={[{ label: "Members", value: "1,284" }, { label: "Waiting", value: "19" }, { label: "Active", value: "1,201" }]} />
          <div className="adm-card adm-tablecard">
            <DataTable<Row> caption="Sample members" columns={columns} data={ROWS} getRowId={(r) => r.id} rowLabel={(r) => r.name} selected={selected} onSelectedChange={setSelected} sort={{ id: "name", desc: false }} onSortChange={() => undefined} />
            <Pager page={0} size={25} total={3} onPage={() => undefined} onSize={() => undefined} />
          </div>
        </div>
      </Both>

      <Both title="Navigation states">
        <ul className="adm-nav__list" style={{ maxWidth: 280 }}>
          <li><span className="adm-nav__link" data-current="true"><span className="adm-nav__label">Active page</span></span></li>
          <li><span className="adm-nav__link"><span className="adm-nav__label">Default page</span></span></li>
          <li><span className="adm-nav__link"><span className="adm-nav__label">With a count</span><span className="adm-nav__count">4</span></span></li>
          <li><span className="adm-nav__link"><span className="adm-nav__label">Not built yet</span><span className="adm-nav__soon">Soon</span></span></li>
        </ul>
      </Both>

      <Both title="Notifications popover and search rows">
        <div className="wo-popover" style={{ maxWidth: 380 }}>
          <div className="wo-notes__head">
            <p className="wo-notes__title">Notifications</p>
            <span className="wo-linkbtn">Mark all as read</span>
          </div>
          <div className="wo-notes__tabs">
            <span className="wo-notes__tab" aria-selected="true">Unread</span>
            <span className="wo-notes__tab" aria-selected="false">All</span>
          </div>
          <ul className="wo-notes__list">
            <li><div className="wo-notes__item" data-unread="true"><span className="wo-notes__icon"><UserCheck size={18} strokeWidth={1.5} /></span><span className="wo-notes__text"><span className="wo-notes__line">Ngozi asked for a session on 14 Oct</span><span className="wo-notes__when">5 minutes ago</span></span><span className="wo-notes__dot" /></div></li>
            <li><div className="wo-notes__item" data-unread="false"><span className="wo-notes__icon"><CalendarDays size={18} strokeWidth={1.5} /></span><span className="wo-notes__text"><span className="wo-notes__line">Demo Day, Lagos is tomorrow</span><span className="wo-notes__when">Yesterday</span></span><span /></div></li>
          </ul>
          <div className="wo-notes__foot"><span className="wo-linkbtn">View all notifications</span></div>
        </div>
        <div className="wo-search__panel" style={{ position: "static", marginTop: 16 }}>
          <div className="wo-search__heading"><span>Members</span></div>
          <div className="wo-search__row" data-active="true"><Search size={18} strokeWidth={1.5} /><span className="wo-search__main"><span className="wo-search__title"><mark>Ada</mark>eze Okafor</span><span className="wo-search__sub">Fintech founder in Lagos</span></span><span className="wo-search__tag">Member</span></div>
          <div className="wo-search__row"><Bell size={18} strokeWidth={1.5} /><span className="wo-search__main"><span className="wo-search__title"><mark>Ada</mark>ptive selling</span><span className="wo-search__sub">Sales</span></span><span className="wo-search__tag">Course</span></div>
        </div>
      </Both>

      <section className="adm-design__section" aria-label="Right side drawer">
        <h2 className="adm-card__title">Right side drawer</h2>
        <p>One panel for forms and long records: contact support, a support ticket, adding a course. Esc and the close button ask first when something was typed.</p>
        <Button variant="secondary" onClick={() => setDrawer(true)}>Open a sample drawer</Button>
        <Drawer
          open={drawer}
          onOpenChange={setDrawer}
          eyebrow="Sample"
          title="Add a course"
          subtitle="Step 1 of 4: the basics"
          dirty={draft !== ""}
          footer={<><Button variant="secondary" onClick={() => setDrawer(false)}>Back</Button><Button onClick={() => setDrawer(false)}>Next</Button></>}
        >
          <label className="wo-label" htmlFor="design-drawer-title">Course title</label>
          <input id="design-drawer-title" className="wo-input" value={draft} onChange={(e) => setDraft(e.target.value)} />
        </Drawer>
      </section>
    </>
  );
}
