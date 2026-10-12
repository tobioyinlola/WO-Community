import { useQuery } from "@tanstack/react-query";
import { LifeBuoy } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { StatusChip } from "../../admin/kit/TableBits";
import { Alert, Button, Tabs } from "../../components";
import { formatDate, timeAgo } from "../../lib/format";
import { STATUS_TONE } from "../../support/constants";
import { useSupport } from "../../support/SupportProvider";
import { EmptyState, PageHeader, SkeletonRows, useDocumentTitle } from "../../ui/blocks";

type Filter = "open" | "resolved" | "all";

/** Everything the member has asked for, newest activity first. */
export function MySupportPage() {
  useDocumentTitle("My support requests");
  const support = useSupport();
  const [filter, setFilter] = useState<Filter>("open");
  const list = useQuery({
    queryKey: ["support", "tickets", filter],
    queryFn: () => unwrap(api.GET("/api/v1/support/tickets", { params: { query: { limit: 50, ...(filter === "all" ? {} : { status: filter }) } } })),
  });
  const rows = list.data?.results ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Support"
        title="My support requests"
        lead="Everything you have asked us for help with, and how it is going."
        actions={<Button onClick={() => support.open()}>New request</Button>}
      />
      <div className="app-tabs-scroll">
        <Tabs
          label="Which requests"
          variant="segment"
          value={filter}
          onChange={(id) => setFilter(id as Filter)}
          items={[
            { id: "open", label: "Open" },
            { id: "resolved", label: "Resolved" },
            { id: "all", label: "All" },
          ]}
        />
      </div>

      {list.isPending ? <SkeletonRows /> : null}
      {list.isError ? (
        <Alert tone="danger" title="We could not load your requests">
          {messageOf(list.error)}
        </Alert>
      ) : null}
      {list.isSuccess && rows.length === 0 ? (
        <EmptyState title={filter === "resolved" ? "Nothing resolved yet" : "No requests"} icon={<LifeBuoy size={22} strokeWidth={1.5} />}>
          {filter === "resolved" ? "Resolved requests appear here." : "When you ask for help, it will be listed here."}
          <div style={{ marginTop: "var(--space-4)" }}>
            <Button onClick={() => support.open()}>Contact support</Button>
          </div>
        </EmptyState>
      ) : null}

      {rows.length > 0 ? (
        <ul className="wo-tickets" aria-label="Your requests">
          {rows.map((t) => (
            <li key={t.id}>
              <Link to={`/app/support/${t.id}`} className="wo-tickets__row">
                <span className="wo-tickets__ref">{t.reference}</span>
                <span className="wo-tickets__main">
                  <span className="wo-tickets__subject">{t.subject}</span>
                  <span className="wo-tickets__meta">
                    {t.category_label} · opened {formatDate(t.created_at)}
                  </span>
                </span>
                <StatusChip tone={STATUS_TONE[t.status]}>{t.status_label}</StatusChip>
                <span className="wo-tickets__when">
                  <time dateTime={t.last_activity_at}>{timeAgo(t.last_activity_at)}</time>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
