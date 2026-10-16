import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mic, MessageCircle, RotateCcw, Send, Square, Volume2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert } from "../components";
import { usePref } from "../admin/shell/prefs";
import { useJob } from "../pages/launch/jobs";
import { useFeature } from "../pages/launch/config";
import { record, Speaker, speechUrl, voiceSupported, voiceTurn, type Recording } from "./onyekaVoice";

type Message = components["schemas"]["TkAdvisorMessage"];
type Conversation = components["schemas"]["TkAdvisorConversation"];
/** Where a spoken conversation is: off, or one of the turns of a back and forth. */
type Phase = "off" | "listening" | "thinking" | "speaking";

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

  // Voice: a back and forth that keeps going until the member stops it.
  const [phase, setPhaseState] = useState<Phase>("off");
  const [level, setLevel] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const voiceOn = useRef(false);
  const recording = useRef<Recording | null>(null);
  const speaking = useRef<AbortController | null>(null);
  const speakerRef = useRef<Speaker | null>(null);
  const speaker = () => (speakerRef.current ??= new Speaker());
  const canSpeak = voiceSupported();
  const setPhase = (next: Phase) => setPhaseState(voiceOn.current ? next : "off");

  const query = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/toolkit/advisor/messages")) });
  const refresh = useCallback(() => client.invalidateQueries({ queryKey: KEY }), [client]);

  const stopVoice = useCallback(() => {
    voiceOn.current = false;
    recording.current?.cancel();
    recording.current = null;
    speaking.current?.abort();
    speakerRef.current?.stop();
    setLevel(0);
    setPhaseState("off");
  }, []);
  useEffect(() => stopVoice, [stopVoice]);

  /** Reads an answer aloud, then listens for the member's reply. Pass the streaming address when
   * the server already gave it, which saves a round trip. */
  const answerAloud = async (messageId: string, url?: string | null) => {
    if (!voiceOn.current) return;
    setPhase("speaking");
    const controller = new AbortController();
    speaking.current = controller;
    try {
      await speaker().play(url ?? (await speechUrl(messageId)), controller.signal);
    } catch (error) {
      setVoiceError(messageOf(error));
      stopVoice();
      return;
    }
    if (voiceOn.current) void listen();
  };

  const running = useJob(jobId, () => {
    setJobId(null);
    void client.refetchQueries({ queryKey: KEY }).then(() => {
      const latest = client.getQueryData<Conversation>(KEY)?.messages.at(-1);
      if (latest?.author === "assistant") void answerAloud(latest.id);
    });
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
      if (result.assistant_message) void answerAloud(result.assistant_message.id);
    },
    // Nothing was sent, so the words go back in the box rather than being lost.
    onError: (_error, body) => {
      if (!voiceOn.current) setText((current) => current || body);
      stopVoice();
    },
    onSettled: () => setPending(null),
  });

  /** Records one spoken turn, turns it into words and sends them. */
  const listen = async () => {
    if (!voiceOn.current) return;
    setVoiceError(null);
    setPhase("listening");
    let turn: Recording;
    try {
      turn = await record(setLevel);
    } catch {
      setVoiceError("Onyeka can't hear you: allow this site to use your microphone in your browser, then try again.");
      stopVoice();
      return;
    }
    if (!voiceOn.current) {
      turn.cancel();
      return;
    }
    recording.current = turn;
    const { blob, end: how } = await turn.done;
    recording.current = null;
    setLevel(0);
    if (!voiceOn.current) return;
    if (!blob) {
      if (how === "silent") setVoiceError("I didn't hear anything. Tap the microphone when you're ready to talk.");
      stopVoice();
      return;
    }
    setPhase("thinking");
    try {
      // One request: the words, Onyeka's short spoken answer, and where to stream it from.
      const turn = await voiceTurn(blob);
      void refresh();
      if (!voiceOn.current) return;
      if (turn.job) setJobId(turn.job.id);
      else if (turn.assistant_message) void answerAloud(turn.assistant_message.id, turn.speech_url);
    } catch (error) {
      setVoiceError(messageOf(error));
      stopVoice();
    }
  };

  const startVoice = () => {
    speaker().unlock(); // inside the tap, so the browser lets the answers play
    setVoiceError(null);
    voiceOn.current = true;
    void listen();
  };

  /** Plays one answer on request, outside a spoken conversation. */
  const listenTo = (id: string) => {
    if (playingId === id) {
      speakerRef.current?.stop();
      setPlayingId(null);
      return;
    }
    speaker().unlock();
    setVoiceError(null);
    setPlayingId(id);
    speechUrl(id)
      .then((url) => speaker().play(url))
      .catch((error: unknown) => setVoiceError(messageOf(error)))
      .finally(() => setPlayingId((current) => (current === id ? null : current)));
  };

  const clear = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/toolkit/advisor/messages")),
    onSuccess: () => {
      client.setQueryData(KEY, (old: typeof query.data) => (old ? { ...old, messages: [] } : old));
      input.current?.focus();
    },
  });

  const messages = query.data?.messages ?? [];
  const thinking = send.isPending || running.running || phase === "thinking";
  const aiOn = query.data?.ai_enabled ?? true;
  const inVoice = phase !== "off";

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, thinking]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (voiceOn.current) stopVoice();
      else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, stopVoice]);

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
          <button type="button" className="onyeka-icon" onClick={() => { stopVoice(); clear.mutate(); }} disabled={clear.isPending || thinking} aria-label="Start over" title="Start over">
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
        {messages.map((m) => (
          <Bubble key={m.id} message={m} playing={playingId === m.id} onListen={canSpeak && aiOn && !inVoice ? () => listenTo(m.id) : undefined} />
        ))}
        {pending ? <div className="onyeka-msg" data-author="user"><p>{pending}</p></div> : null}
        {thinking ? (
          <div className="onyeka-msg onyeka-msg--typing" role="status">
            <span className="wo-visually-hidden">Onyeka is thinking</span>
            <span className="onyeka-dots" aria-hidden="true"><i /><i /><i /></span>
          </div>
        ) : null}
        {running.failure ? <Alert tone="danger" title="Onyeka could not answer">{running.failure.error_detail || "Please try again."}</Alert> : null}
        {send.error ? <Alert tone="danger" title="Not sent">{messageOf(send.error)}</Alert> : null}
        {voiceError ? <Alert tone="warning" title="Voice">{voiceError}</Alert> : null}
        {!aiOn ? <Alert tone="info" title="Onyeka is resting">AI answers are not switched on right now. Please try again later.</Alert> : null}
        {!messages.length && !thinking && !inVoice && aiOn && query.isSuccess ? (
          <div className="onyeka-starters">
            {STARTERS.map((s) => (
              <button key={s} type="button" className="onyeka-chip" onClick={() => submit(s)}>{s}</button>
            ))}
          </div>
        ) : null}
        <div ref={end} />
      </div>

      {inVoice ? (
        <VoiceBar
          phase={phase}
          level={level}
          onDone={() => recording.current?.finish()}
          onSkip={() => speaking.current?.abort()}
          onStop={stopVoice}
        />
      ) : (
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
          {canSpeak && aiOn && !text.trim() ? (
            <button type="button" className="onyeka-send onyeka-send--mic" onClick={startVoice} disabled={thinking} aria-label="Talk to Onyeka" title="Talk to Onyeka">
              <Mic size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
          ) : (
            <button type="submit" className="onyeka-send" disabled={!text.trim() || thinking || !aiOn} aria-label="Send">
              <Send size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
          )}
        </form>
      )}
      <p className="onyeka-panel__note">AI guidance, not legal, tax or investment advice.</p>
    </section>
  );
}

const PHASE_TEXT: Record<Exclude<Phase, "off">, string> = {
  listening: "Listening… pause when you're done",
  thinking: "Onyeka is thinking…",
  speaking: "Onyeka is speaking",
};

function VoiceBar({ phase, level, onDone, onSkip, onStop }: { phase: Exclude<Phase, "off">; level: number; onDone: () => void; onSkip: () => void; onStop: () => void }) {
  return (
    <div className="onyeka-voice" role="group" aria-label="Voice conversation">
      <span className="onyeka-voice__orb" data-phase={phase} style={{ ["--level" as string]: String(phase === "listening" ? level : 0) }} aria-hidden="true">
        {phase === "speaking" ? <Volume2 size={20} strokeWidth={1.75} /> : <Mic size={20} strokeWidth={1.75} />}
      </span>
      <p className="onyeka-voice__text" role="status">{PHASE_TEXT[phase]}</p>
      {phase === "listening" ? <button type="button" className="onyeka-voice__btn" onClick={onDone}>Done</button> : null}
      {phase === "speaking" ? <button type="button" className="onyeka-voice__btn" onClick={onSkip}>Skip</button> : null}
      <button type="button" className="onyeka-voice__btn onyeka-voice__btn--stop" onClick={onStop} aria-label="End voice conversation" title="End voice conversation">
        <Square size={14} strokeWidth={2} aria-hidden="true" /> End
      </button>
    </div>
  );
}

function Bubble({ message, playing, onListen }: { message: Message; playing: boolean; onListen?: () => void }) {
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
      {message.author === "assistant" && onListen ? (
        <button type="button" className="onyeka-listen" onClick={onListen} aria-pressed={playing}>
          {playing ? <Square size={12} strokeWidth={2} aria-hidden="true" /> : <Volume2 size={14} strokeWidth={1.75} aria-hidden="true" />}
          {playing ? "Stop" : "Listen"}
        </button>
      ) : null}
    </div>
  );
}
