import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, MapPin, Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useCursorList } from "../../api/hooks";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { Alert, Badge, Button, Card, CardTo, CardText, CardTitle, Tabs } from "../../components";
import { formatDate, formatDateTime, formatTime, humanise, plural } from "../../lib/format";
import { EmptyState, LoadMore, Loaded, PageHeader, RichText, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { DownloadButton } from "../../ui/DownloadButton";
import { useToast } from "../../ui/Toast";

type EventSummary = components["schemas"]["EventSummary"];
type When = "upcoming" | "past" | "mine";

function dayOf(iso: string) {
  const d = new Date(iso);
  return {
    day: new Intl.DateTimeFormat("en-GB", { day: "numeric" }).format(d),
    month: new Intl.DateTimeFormat("en-GB", { month: "short" }).format(d),
  };
}

function EventCard({ event }: { event: EventSummary }) {
  const { day, month } = dayOf(event.starts_at);
  return (
    <CardTo to={`/app/events/${event.id}`}>
      <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <div className="app-tile" style={{ flexDirection: "column", width: 56, height: 64, lineHeight: 1.1 }} aria-hidden="true">
          <strong style={{ font: "800 22px/1 var(--font-display)" }}>{day}</strong>
          <span className="caption">{month}</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="app-cluster" style={{ marginBottom: "var(--space-2)" }}>
            <Badge variant="investor">{humanise(event.type)}</Badge>
            {event.status === "cancelled" ? <Badge variant="danger" dot>Cancelled</Badge> : null}
            {event.registered ? <Badge variant="success" dot>Registered</Badge> : null}
            {event.spots_left === 0 && !event.registered ? <Badge variant="warning" dot>Full</Badge> : null}
          </div>
          <CardTitle>{event.title}</CardTitle>
          <CardText>{event.excerpt}</CardText>
          <ul className="app-meta" style={{ marginTop: "var(--space-3)" }}>
            <li>{formatTime(event.starts_at)}</li>
            {event.location ? (
              <li>
                <MapPin size={14} strokeWidth={1.5} aria-hidden="true" />
                {event.location}
              </li>
            ) : null}
          </ul>
        </div>
      </div>
    </CardTo>
  );
}

export default function EventsPage() {
  const [when, setWhen] = useState<When>("upcoming");
  const list = useCursorList<EventSummary>(["events", when], (cursor) =>
    unwrap(
      api.GET("/api/v1/events", {
        params: {
          query: {
            limit: 12,
            when: when === "past" ? "past" : "upcoming",
            ...(when === "mine" ? { registered: true } : {}),
            ...(cursor ? { cursor } : {}),
          },
        },
      }),
    ),
  );
  return (
    <>
      <PageHeader eyebrow="Events" title="Events" lead="Demo days, workshops and meetups. Register to get reminders." />
      <div className="app-tabs-scroll">
        <Tabs
          label="Which events"
          value={when}
          onChange={(id) => setWhen(id as When)}
          items={[
            { id: "upcoming", label: "Upcoming" },
            { id: "mine", label: "I am going" },
            { id: "past", label: "Past" },
          ]}
        />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load events">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? (
        <EmptyState title={when === "mine" ? "You have not registered for anything" : "Nothing here yet"}>
          {when === "mine" ? "Register for an upcoming event and it will appear here." : "New events are announced regularly."}
        </EmptyState>
      ) : null}
      <div className="app-grid app-grid--wide">
        {list.items.map((event) => (
          <EventCard key={event.id} event={event} />
        ))}
      </div>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

export function EventDetail() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ["events", "one", id],
    queryFn: () => unwrap(api.GET("/api/v1/events/{event_id}", { params: { path: { event_id: id } } })),
  });
  const toggle = useMutation({
    mutationFn: (register: boolean) =>
      register
        ? unwrap(api.POST("/api/v1/events/{event_id}/register", { params: { path: { event_id: id } } }))
        : unwrap(api.DELETE("/api/v1/events/{event_id}/register", { params: { path: { event_id: id } } })),
    onSuccess: async (result) => {
      toast.show(result.registered ? "You are registered. We will remind you." : "Registration cancelled");
      await client.invalidateQueries({ queryKey: ["events"] });
    },
  });

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(event) => (
        <>
          <PageHeader
            eyebrow={humanise(event.type)}
            title={event.title}
            lead={`${formatDate(event.starts_at)}, ${formatTime(event.starts_at)} to ${formatTime(event.ends_at)}`}
          />
          <div className="app-split">
            <Card>
              <div className="app-stack app-stack--lg">
                <RichText html={event.description} />
                {event.summary ? (
                  <>
                    <h2 className="h4" style={{ margin: 0 }}>What happened</h2>
                    <RichText html={event.summary} />
                  </>
                ) : null}
                {event.recording_url ? (
                  <a className="app-link" href={event.recording_url} target="_blank" rel="noopener noreferrer">
                    Watch the recording
                  </a>
                ) : null}
                {event.slots.length > 0 ? (
                  <>
                    <h2 className="h4" style={{ margin: 0 }}>Pitching on the day</h2>
                    <ol className="app-stack" style={{ margin: 0, paddingLeft: "var(--space-6)" }}>
                      {event.slots.map((slot) => (
                        <li key={slot.position}>{slot.startup.name}</li>
                      ))}
                    </ol>
                  </>
                ) : null}
              </div>
            </Card>
            <aside className="app-stack">
              <Card>
                <ul className="app-meta" style={{ flexDirection: "column", gap: "var(--space-2)" }}>
                  <li>{formatDateTime(event.starts_at)}</li>
                  {event.location ? (<li><MapPin size={16} strokeWidth={1.5} aria-hidden="true" />{event.location}</li>) : null}
                  <li>
                    <Users size={16} strokeWidth={1.5} aria-hidden="true" />
                    {plural(event.registered_count, "person", "people")} going
                    {event.spots_left !== null ? `, ${plural(event.spots_left, "spot")} left` : ""}
                  </li>
                </ul>
                {toggle.isError ? <div style={{ marginTop: "var(--space-4)" }}><Alert tone="danger" title="That did not work">{messageOf(toggle.error)}</Alert></div> : null}
                <div className="app-stack" style={{ marginTop: "var(--space-6)" }}>
                  {event.past ? (
                    <Alert tone="info" title="This event has finished" />
                  ) : event.registered ? (
                    <>
                      <Alert tone="success" title="You are registered" />
                      <Button variant="secondary" loading={toggle.isPending} onClick={() => toggle.mutate(false)}>
                        Cancel my place
                      </Button>
                    </>
                  ) : (
                    <Button size="lg" loading={toggle.isPending} disabled={!event.registration_open || event.spots_left === 0} onClick={() => toggle.mutate(true)}>
                      {event.spots_left === 0 ? "Event is full" : "Register"}
                    </Button>
                  )}
                  <DownloadButton variant="secondary" path={`/api/v1/events/${event.id}/calendar.ics`} filename={`${event.slug}.ics`} icon={<CalendarPlus size={18} strokeWidth={1.5} aria-hidden="true" />}>
                    Add to calendar
                  </DownloadButton>
                  {event.link && event.registered ? (
                    <a className="wo-btn wo-btn--accent" href={event.link} target="_blank" rel="noopener noreferrer">
                      Join online
                    </a>
                  ) : null}
                </div>
              </Card>
              <Link className="app-link" to="/app/events">All events</Link>
            </aside>
          </div>
        </>
      )}
    </Loaded>
  );
}
