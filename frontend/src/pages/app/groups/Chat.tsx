import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CornerUpLeft, LogOut, MoreHorizontal, SendHorizontal, Smile, SmilePlus, Trash2, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../../api/client";
import { messageOf } from "../../../api/errors";
import type { components } from "../../../api/schema";
import { Avatar, Button, Modal } from "../../../components";
import { SkeletonRows } from "../../../ui/blocks";
import { useToast } from "../../../ui/Toast";
import { QUICK_REACTIONS } from "./emoji";
import { EmojiPicker } from "./EmojiPicker";

export type ChatGroup = components["schemas"]["ChatGroup"];
type Message = components["schemas"]["GroupMessage"];
type Reaction = components["schemas"]["GroupReactionCount"];

const POLL_MS = 4000;
const GAP_MS = 5 * 60 * 1000; // messages closer than this from one person read as one block

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function dayLabel(iso: string): string {
  const day = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(day, today)) return "Today";
  if (same(day, yesterday)) return "Yesterday";
  return day.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: day.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}

/** Messages by id, oldest first: each fetch adds what is new and refreshes what changed. */
function merge(map: Map<string, Message>, rows: Message[]): Map<string, Message> {
  const next = new Map(map);
  for (const m of rows) next.set(m.id, m);
  return new Map([...next.entries()].sort((a, b) => a[1].created_at.localeCompare(b[1].created_at) || a[0].localeCompare(b[0])));
}

export function Chat({ group, onBack }: { group: ChatGroup; onBack?: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const path = { group_id: group.id };
  const latest = useQuery({
    queryKey: ["groups", group.id, "messages"],
    queryFn: () => unwrap(api.GET("/api/v1/groups/{group_id}/messages", { params: { path } })),
    refetchInterval: POLL_MS,
  });
  const [all, setAll] = useState<Map<string, Message>>(new Map());
  const [older, setOlder] = useState<string | null | undefined>(undefined);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [picker, setPicker] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"leave" | Message | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);
  const keepOffset = useRef<number | null>(null);

  const seen = useRef(new Set<string>());
  useEffect(() => {
    if (!latest.data) return;
    const fresh = latest.data.results.filter((m) => !seen.current.has(m.id));
    fresh.forEach((m) => seen.current.add(m.id));
    setAll((prev) => merge(prev, latest.data.results));
    setOlder((prev) => (prev === undefined ? latest.data.older : prev));
    // Reading marks the group read, so the list's unread counts and last line change with it.
    if (fresh.length) void client.invalidateQueries({ queryKey: ["groups", "list"] });
  }, [latest.data, client]);

  const messages = useMemo(() => [...all.values()], [all]);

  // New messages keep you at the bottom if you were there; loading earlier ones keeps your place.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (keepOffset.current !== null) {
      el.scrollTop = el.scrollHeight - keepOffset.current;
      keepOffset.current = null;
    } else if (stickToBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const onScroll = () => {
    const el = scroller.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const loadEarlier = async () => {
    if (!older) return;
    setLoadingOlder(true);
    try {
      const page = await unwrap(api.GET("/api/v1/groups/{group_id}/messages", { params: { path, query: { cursor: older } } }));
      const el = scroller.current;
      keepOffset.current = el ? el.scrollHeight - el.scrollTop : null;
      setAll((prev) => merge(prev, page.results));
      setOlder(page.older);
    } catch (e) {
      toast.show(messageOf(e));
    } finally {
      setLoadingOlder(false);
    }
  };

  const send = async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      const sent = await unwrap(api.POST("/api/v1/groups/{group_id}/messages", { params: { path }, body: { body, reply_to: replyTo?.id ?? null } }));
      stickToBottom.current = true;
      setAll((prev) => merge(prev, [sent]));
      setText("");
      setReplyTo(null);
      input.current?.focus();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setSending(false);
    }
  };

  const react = useCallback(
    async (message: Message, emoji: string) => {
      try {
        const result = await unwrap(api.POST("/api/v1/group-messages/{message_id}/reactions", { params: { path: { message_id: message.id } }, body: { emoji } }));
        setAll((prev) => {
          const current = prev.get(message.id);
          return current ? merge(prev, [{ ...current, reactions: result.reactions }]) : prev;
        });
      } catch (e) {
        toast.show(messageOf(e));
      }
    },
    [toast],
  );

  const remove = async (message: Message) => {
    try {
      await unwrap(api.DELETE("/api/v1/group-messages/{message_id}", { params: { path: { message_id: message.id } } }));
      setAll((prev) => merge(prev, [{ ...message, deleted: true, body: "", reactions: [] }]));
    } catch (e) {
      toast.show(messageOf(e));
    }
    setConfirm(null);
  };

  const leave = async () => {
    try {
      await unwrap(api.DELETE("/api/v1/groups/{group_id}/membership", { params: { path } }));
      await client.invalidateQueries({ queryKey: ["groups", "list"] });
      toast.show(`You left ${group.name}`);
      onBack?.();
    } catch (e) {
      toast.show(messageOf(e));
    }
    setConfirm(null);
  };

  const insert = (emoji: string) => {
    const el = input.current;
    const start = el?.selectionStart ?? text.length;
    const end = el?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + emoji + text.slice(end);
    setText(next);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + emoji.length, start + emoji.length);
    });
  };

  return (
    <section className="wo-chat" aria-label={`${group.name} chat`}>
      <header className="wo-chat__head">
        {onBack ? (
          <button type="button" className="wo-chat__icon wo-chat__back" onClick={onBack} aria-label="All groups">
            <ArrowLeft size={20} strokeWidth={1.75} aria-hidden="true" />
          </button>
        ) : null}
        <span className="wo-group__emoji" aria-hidden="true">{group.emoji || "💬"}</span>
        <div className="wo-chat__title">
          <h2>{group.name}</h2>
          <p>{group.member_count} {group.member_count === 1 ? "member" : "members"}</p>
        </div>
        <Button variant="ghost" size="sm" icon={<LogOut size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => setConfirm("leave")}>
          Leave
        </Button>
      </header>

      <div className="wo-chat__scroll" ref={scroller} onScroll={onScroll} aria-live="polite" aria-relevant="additions">
        {older ? (
          <div className="wo-chat__earlier">
            <Button variant="secondary" size="sm" loading={loadingOlder} onClick={() => void loadEarlier()}>Load earlier messages</Button>
          </div>
        ) : null}
        {latest.isPending ? <SkeletonRows count={4} /> : null}
        {latest.isSuccess && messages.length === 0 ? (
          <div className="wo-chat__empty">
            <span aria-hidden="true">{group.emoji || "💬"}</span>
            <p><strong>Say hello to {group.name}.</strong></p>
            <p>Be the first to start the conversation.</p>
          </div>
        ) : null}
        {messages.map((m, i) => {
          const prev = messages[i - 1];
          const newDay = !prev || new Date(prev.created_at).toDateString() !== new Date(m.created_at).toDateString();
          const joined = !newDay && prev && prev.author.id === m.author.id && new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() < GAP_MS;
          return (
            <Fragment key={m.id}>
              {newDay ? <p className="wo-chat__day"><span>{dayLabel(m.created_at)}</span></p> : null}
              <Bubble message={m} joined={Boolean(joined)} onReact={react} onReply={() => { setReplyTo(m); input.current?.focus(); }} onDelete={() => setConfirm(m)} />
            </Fragment>
          );
        })}
      </div>

      <form
        className="wo-chat__compose"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        {replyTo ? (
          <div className="wo-chat__replying">
            <CornerUpLeft size={16} strokeWidth={1.75} aria-hidden="true" />
            <span>Replying to <strong>{replyTo.author.name}</strong>: {replyTo.body.slice(0, 80)}</span>
            <button type="button" className="wo-chat__icon" aria-label="Cancel reply" onClick={() => setReplyTo(null)}>
              <X size={16} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
        ) : null}
        {error ? <p className="wo-chat__error" role="alert">{error}</p> : null}
        <div className="wo-chat__row">
          <div className="wo-chat__emojiwrap">
            <button type="button" className="wo-chat__icon" aria-label="Add an emoji" aria-expanded={picker} onClick={() => setPicker((v) => !v)}>
              <Smile size={22} strokeWidth={1.75} aria-hidden="true" />
            </button>
            {picker ? <EmojiPicker stayOpen onPick={insert} onClose={() => setPicker(false)} /> : null}
          </div>
          <label className="wo-visually-hidden" htmlFor={`chat-${group.id}`}>Message {group.name}</label>
          <textarea
            id={`chat-${group.id}`}
            ref={input}
            className="wo-chat__input"
            rows={1}
            maxLength={2000}
            placeholder={`Message ${group.name}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button type="submit" className="wo-chat__send" aria-label="Send" disabled={!text.trim() || sending}>
            <SendHorizontal size={20} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
      </form>

      {confirm === "leave" ? (
        <Modal
          open
          onClose={() => setConfirm(null)}
          title={`Leave ${group.name}?`}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirm(null)}>Stay</Button>
              <Button variant="danger" onClick={() => void leave()}>Leave group</Button>
            </>
          }
        >
          You stop seeing its messages. You can join again at any time.
        </Modal>
      ) : confirm ? (
        <Modal
          open
          onClose={() => setConfirm(null)}
          title="Delete this message?"
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirm(null)}>Keep it</Button>
              <Button variant="danger" onClick={() => void remove(confirm)}>Delete</Button>
            </>
          }
        >
          Everyone in the group will see that a message was deleted.
        </Modal>
      ) : null}
    </section>
  );
}

function Bubble({
  message: m,
  joined,
  onReact,
  onReply,
  onDelete,
}: {
  message: Message;
  joined: boolean;
  onReact: (m: Message, emoji: string) => void;
  onReply: () => void;
  onDelete: () => void;
}) {
  const [picker, setPicker] = useState(false);
  const [open, setOpen] = useState(false);
  const gone = m.deleted;
  return (
    <div
      className={`wo-msg${m.mine ? " wo-msg--mine" : ""}${joined ? " wo-msg--joined" : ""}${open || picker ? " wo-msg--active" : ""}`}
    >
      {!m.mine ? (
        <div className="wo-msg__avatar" aria-hidden={joined}>
          {joined ? null : <Avatar name={m.author.name} id={m.author.id} src={m.author.photo?.thumb} size="sm" />}
        </div>
      ) : null}
      <div className="wo-msg__main">
        {!joined ? (
          <p className="wo-msg__meta">
            {m.mine ? null : (
              <Link className="wo-msg__name" to={`/app/members/${m.author.id}`}>
                {m.author.name}
              </Link>
            )}
            <time dateTime={m.created_at}>{time(m.created_at)}</time>
          </p>
        ) : null}
        <div className={`wo-msg__bubble${gone ? " wo-msg__bubble--gone" : ""}`} title={joined ? time(m.created_at) : undefined}>
          {m.reply_to && !gone ? (
            <p className="wo-msg__quote">
              <strong>{m.reply_to.author}</strong>
              <span>{m.reply_to.deleted ? "Message deleted" : m.reply_to.text}</span>
            </p>
          ) : null}
          {gone ? <em>{m.removed ? "Removed by the community team" : "This message was deleted"}</em> : <span className="wo-msg__text">{m.body}</span>}
        </div>
        {m.reactions.length ? (
          <div className="wo-msg__reactions">
            {m.reactions.map((r: Reaction) => (
              <button
                key={r.emoji}
                type="button"
                className={`wo-reaction${r.mine ? " wo-reaction--mine" : ""}`}
                aria-pressed={r.mine}
                aria-label={`${r.emoji} ${r.count}${r.mine ? ", including you" : ""}`}
                onClick={() => onReact(m, r.emoji)}
              >
                <span aria-hidden="true">{r.emoji}</span> {r.count}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {!gone ? (
        <button
          type="button"
          className="wo-msg__more"
          aria-label="Message actions"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <MoreHorizontal size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
      ) : null}
      {!gone ? (
        <div className="wo-msg__tools" role="toolbar" aria-label="Message actions">
          {QUICK_REACTIONS.map((e) => (
            <button key={e} type="button" className="wo-msg__tool wo-msg__tool--emoji" aria-label={`React with ${e}`} onClick={() => onReact(m, e)}>
              {e}
            </button>
          ))}
          <span className="wo-msg__morewrap">
            <button type="button" className="wo-msg__tool" aria-label="More reactions" aria-expanded={picker} onClick={() => setPicker((v) => !v)}>
              <SmilePlus size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
            {picker ? <EmojiPicker align={m.mine ? "end" : "start"} label="React with an emoji" onPick={(e) => onReact(m, e)} onClose={() => setPicker(false)} /> : null}
          </span>
          <button type="button" className="wo-msg__tool" aria-label="Reply" onClick={onReply}>
            <CornerUpLeft size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
          {m.mine ? (
            <button type="button" className="wo-msg__tool" aria-label="Delete" onClick={onDelete}>
              <Trash2 size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
