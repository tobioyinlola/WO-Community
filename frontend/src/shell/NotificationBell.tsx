import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BookOpen, Briefcase, CalendarDays, LifeBuoy, MessageSquare, ShieldCheck, UserCheck, Users, type LucideIcon } from "lucide-react";
import { useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { timeAgo } from "../lib/format";
import { localLink } from "../lib/links";
import "../styles/shared-ui.css";

type Item = components["schemas"]["NotificationItem"];

const COUNT_KEY = ["notifications", "unread-count"] as const;
const SHOWN = 8;

/** One icon for each kind of thing a notification can be about. */
function iconFor(type: string): LucideIcon {
  if (type.startsWith("session") || type.startsWith("mentor")) return UserCheck;
  if (type.startsWith("event")) return CalendarDays;
  if (type.startsWith("job")) return Briefcase;
  if (type.startsWith("course") || type.startsWith("certificate") || type.startsWith("enrol")) return BookOpen;
  if (type.startsWith("ticket") || type.startsWith("support")) return LifeBuoy;
  if (type.startsWith("referral") || type === "new_follower") return Users;
  if (type === "comment" || type === "reply" || type === "mention") return MessageSquare;
  if (type.includes("approved") || type.includes("decision") || type.startsWith("report")) return ShieldCheck;
  return Bell;
}

interface BellProps {
  /** False for an account that has no notification centre, such as an admin who is not a member. */
  enabled?: boolean;
  /** The class of the round button, so the bell sits in either top bar. */
  className?: string;
  /** Where "View all notifications" goes. */
  allHref?: string;
}

/**
 * The bell: an unread badge that is polled, and a popover with the latest notifications. Choosing one
 * marks it read and goes to what it is about.
 */
export function NotificationBell({ enabled = true, className = "adm-iconbtn adm-iconbtn--ring", allHref = "/app/notifications" }: BellProps) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"unread" | "all">("unread");
  const listRef = useRef<HTMLUListElement>(null);

  // The server answers 304 when nothing changed, so a poll costs almost nothing.
  const count = useQuery({
    queryKey: COUNT_KEY,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/notifications/unread-count")),
    refetchInterval: 45_000,
    refetchOnWindowFocus: true,
    staleTime: 20_000,
  });
  const unread = count.data?.unread_count ?? 0;

  const list = useQuery({
    queryKey: ["notifications", "popover", tab],
    enabled: enabled && open,
    queryFn: () =>
      unwrap(api.GET("/api/v1/notifications", { params: { query: { limit: SHOWN, ...(tab === "unread" ? { unread: true } : {}) } } })),
  });

  const mark = useMutation({
    mutationFn: (body: { ids?: string[]; all?: boolean }) => unwrap(api.POST("/api/v1/notifications/read", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const choose = (item: Item) => {
    if (!item.read) mark.mutate({ ids: [item.id] });
    setOpen(false);
    navigate(localLink(item.link));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Home" && event.key !== "End") return;
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    if (buttons.length === 0) return;
    event.preventDefault();
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? Math.min(buttons.length - 1, at + 1) : Math.max(0, at - 1);
    buttons[next]?.focus();
  };

  if (!enabled) return null;

  const items = list.data?.results ?? [];
  const label = unread > 0 ? `Notifications, ${unread} unread` : "Notifications";

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button type="button" className={className} aria-label={label} aria-haspopup="dialog" aria-expanded={open}>
          <Bell size={20} strokeWidth={1.5} aria-hidden="true" />
          {unread > 0 ? (
            <span className="wo-bell__badge" aria-hidden="true">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="wo-popover" align="end" sideOffset={10} collisionPadding={16} aria-label="Notifications">
          <div className="wo-notes__head">
            <h2 className="wo-notes__title">Notifications</h2>
            <button type="button" className="wo-linkbtn" disabled={unread === 0 || mark.isPending} onClick={() => mark.mutate({ all: true })}>
              Mark all as read
            </button>
          </div>
          <div className="wo-notes__tabs" role="tablist" aria-label="Which notifications">
            {(["unread", "all"] as const).map((id) => (
              <button key={id} type="button" role="tab" className="wo-notes__tab" aria-selected={tab === id} onClick={() => setTab(id)}>
                {id === "unread" ? "Unread" : "All"}
              </button>
            ))}
          </div>

          {list.isPending ? (
            <p className="wo-notes__empty" role="status">
              Loading
            </p>
          ) : list.isError ? (
            <p className="wo-notes__empty" role="alert">
              <strong>We could not load notifications</strong>
              Try again in a moment.
            </p>
          ) : items.length === 0 ? (
            <p className="wo-notes__empty" role="status">
              <strong>{tab === "unread" ? "You're all caught up" : "No notifications yet"}</strong>
              {tab === "unread" ? "Nothing new since you last looked." : "Replies, requests and reminders show up here."}
            </p>
          ) : (
            // Arrow keys move between the items; each is a real button.
            // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
            <ul className="wo-notes__list" ref={listRef} onKeyDown={onKeyDown}>
              {items.map((item) => {
                const Icon = iconFor(item.type);
                return (
                  <li key={item.id}>
                    <button type="button" className="wo-notes__item" data-unread={!item.read} onClick={() => choose(item)}>
                      <span className="wo-notes__icon" aria-hidden="true">
                        <Icon size={18} strokeWidth={1.5} />
                      </span>
                      <span className="wo-notes__text">
                        <span className="wo-notes__line">{item.title}</span>
                        <time className="wo-notes__when" dateTime={item.created_at}>
                          {timeAgo(item.created_at)}
                        </time>
                      </span>
                      {item.read ? <span /> : <span className="wo-notes__dot" role="img" aria-label="Unread" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="wo-notes__foot">
            <Link to={allHref} className="wo-linkbtn" onClick={() => setOpen(false)}>
              View all notifications
            </Link>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
