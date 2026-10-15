import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, RotateCcw, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert } from "../components";
import { usePref } from "../admin/shell/prefs";
import { useJob } from "../pages/launch/jobs";
import { useFeature } from "../pages/launch/config";

type Message = components["schemas"]["TkAdvisorMessage"];

const KEY = ["toolkit", "advisor"];
const FRAMEWORK_LABELS: Record<string, string> = {
  yc: "Y Combinator",
  techstars: "Techstars",
  antler: "Antler",
  founder_institute: "Founder Institute",
};
const STARTERS = [
  "Am I ready to apply to Y Combinator?",
  "How do I validate my idea before building?",
  "What would Techstars want to see from us?",
  "How do I find the right co-founder?",
];

/** Onyeka, the community's AI founder advisor: a chat that opens from the corner of every page. */
export function Onyeka({ allowed }: { allowed: boolean }) {
  const on = useFeature("advisor");
  if (!allowed || !on) return null;
  return <OnyekaChat />;
}

function OnyekaChat() {
  const [open, setOpen] = usePref("onyeka-open", false);
  const launcher = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    launcher.current?.focus();
  }, [setOpen]);
  return (
    <>
      {open ? <Panel onClose={close} /> : null}
      <button
        ref={launcher}
        type="button"
        className="onyeka-launcher"
        aria-expanded={open}
        aria-controls="onyeka-panel"
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className="onyeka-avatar" aria-hidden="true">O</span>
        <span className="onyeka-launcher__text">{open ? "Close chat" : "Ask Onyeka"}</span>
      </button>
    </>
  );
}

function Panel({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  const query = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/toolkit/advisor/messages")) });
  const refresh = useCallback(() => client.invalidateQueries({ queryKey: KEY }), [client]);
  const running = useJob(jobId, () => {
    setJobId(null);
    void refresh();
  });

  const send = useMutation({
    mutationFn: (body: string) => unwrap(api.POST("/api/v1/toolkit/advisor/messages", { body: { text: body } })),
    onMutate: (body) => {
      setPending(body);
      setText("");
    },
    onSuccess: (result) => {
      if (result.job) setJobId(result.job.id);
      void refresh();
    },
    // Nothing was sent, so the words go back in the box rather than being lost.
    onError: (_error, body) => setText((current) => current || body),
    onSettled: () => setPending(null),
  });

  const clear = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/toolkit/advisor/messages")),
    onSuccess: () => {
      client.setQueryData(KEY, (old: typeof query.data) => (old ? { ...old, messages: [] } : old));
      input.current?.focus();
    },
  });

  const messages = query.data?.messages ?? [];
  const thinking = send.isPending || running.running;
  const aiOn = query.data?.ai_enabled ?? true;

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, thinking]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (body: string) => {
    const trimmed = body.trim();
    if (!trimmed || thinking || !aiOn) return;
    send.mutate(trimmed);
  };

  return (
    <section className="onyeka-panel" id="onyeka-panel" role="dialog" aria-modal="false" aria-labelledby="onyeka-title">
      <header className="onyeka-panel__head">
        <span className="onyeka-avatar onyeka-avatar--lg" aria-hidden="true">O</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h2 className="onyeka-panel__title" id="onyeka-title">Onyeka</h2>
          <p className="onyeka-panel__sub">Founder, WO Community <span className="onyeka-tag">AI advisor</span></p>
        </div>
        {messages.length ? (
          <button type="button" className="onyeka-icon" onClick={() => clear.mutate()} disabled={clear.isPending || thinking} aria-label="Start over" title="Start over">
            <RotateCcw size={18} strokeWidth={1.5} aria-hidden="true" />
          </button>
        ) : null}
        <button type="button" className="onyeka-icon" onClick={onClose} aria-label="Close chat" title="Close">
          <X size={18} strokeWidth={1.5} aria-hidden="true" />
        </button>
      </header>

      <div className="onyeka-panel__body" aria-live="polite">
        {query.isError ? <Alert tone="danger" title="Could not load the conversation">{messageOf(query.error)}</Alert> : null}
        <div className="onyeka-msg" data-author="assistant">
          <p>{query.data?.greeting ?? "Hi, I'm Onyeka, founder of WO Community, here as your AI advisor."}</p>
        </div>
        {messages.map((m) => <Bubble key={m.id} message={m} />)}
        {pending ? <div className="onyeka-msg" data-author="user"><p>{pending}</p></div> : null}
        {thinking ? (
          <div className="onyeka-msg onyeka-msg--typing" role="status">
            <span className="wo-visually-hidden">Onyeka is thinking</span>
            <span className="onyeka-dots" aria-hidden="true"><i /><i /><i /></span>
          </div>
        ) : null}
        {running.failure ? <Alert tone="danger" title="Onyeka could not answer">{running.failure.error_detail || "Please try again."}</Alert> : null}
        {send.error ? <Alert tone="danger" title="Not sent">{messageOf(send.error)}</Alert> : null}
        {!aiOn ? <Alert tone="info" title="Onyeka is resting">AI answers are not switched on right now. Please try again later.</Alert> : null}
        {!messages.length && !thinking && aiOn && query.isSuccess ? (
          <div className="onyeka-starters">
            {STARTERS.map((s) => (
              <button key={s} type="button" className="onyeka-chip" onClick={() => submit(s)}>{s}</button>
            ))}
          </div>
        ) : null}
        <div ref={end} />
      </div>

      <form className="onyeka-panel__foot" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <label className="wo-visually-hidden" htmlFor="onyeka-input">Message Onyeka</label>
        <textarea
          id="onyeka-input"
          ref={input}
          className="onyeka-input"
          rows={2}
          maxLength={2000}
          placeholder={aiOn ? "Ask about your business…" : "Onyeka is not available right now"}
          disabled={!aiOn}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit(text);
            }
          }}
        />
        <button type="submit" className="onyeka-send" disabled={!text.trim() || thinking || !aiOn} aria-label="Send">
          <Send size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </form>
      <p className="onyeka-panel__note">AI guidance, not legal, tax or investment advice.</p>
    </section>
  );
}

function Bubble({ message }: { message: Message }) {
  return (
    <div className="onyeka-msg" data-author={message.author}>
      {message.text.split(/\n{2,}/).map((para, i) => <p key={i}>{para}</p>)}
      {message.next_steps.length ? (
        <>
          <p className="onyeka-msg__label">Next steps</p>
          <ol className="onyeka-steps">{message.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </>
      ) : null}
      {message.frameworks.length ? (
        <p className="onyeka-msg__drew">
          <MessageCircle size={14} strokeWidth={1.5} aria-hidden="true" /> Drawing on {message.frameworks.map((f) => FRAMEWORK_LABELS[f] ?? f).join(", ")}
        </p>
      ) : null}
    </div>
  );
}
