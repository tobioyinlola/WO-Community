import type { ColumnDef } from "@tanstack/react-table";
import { useState, type ReactNode } from "react";
import { Avatar, Button } from "../components";
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
    </>
  );
}
