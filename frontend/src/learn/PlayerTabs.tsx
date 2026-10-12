import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Button, Textarea } from "../components";
import { formatClock, timeAgo } from "../lib/format";
import { EmptyState, SkeletonRows } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import "../styles/learn.css";

type Question = components["schemas"]["Question"];

function AnswerForm({ questionId, onDone }: { questionId: string; onDone: () => void }) {
  const [body, setBody] = useState("");
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/questions/{question_id}/answers", { params: { path: { question_id: questionId } }, body: { body } })),
    onSuccess: async () => {
      setBody("");
      onDone();
      await client.invalidateQueries({ queryKey: ["lesson-questions"] });
    },
  });
  return (
    <form
      className="wo-qa__answerform"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (body.trim()) send.mutate();
      }}
    >
      <Textarea label="Your answer" rows={3} maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
      {send.isError ? <Alert tone="danger" title="We could not post your answer">{messageOf(send.error)}</Alert> : null}
      <div className="wo-qa__row">
        <Button type="submit" size="sm" loading={send.isPending} disabled={!body.trim()}>
          Post answer
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Questions on this lecture. Anyone enrolled can ask or answer; staff answers carry a badge. */
export function Questions({ lessonId }: { lessonId: string }) {
  const client = useQueryClient();
  const [body, setBody] = useState("");
  const [answering, setAnswering] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["lesson-questions", lessonId],
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/questions", { params: { path: { lesson_id: lessonId } } })),
  });
  const ask = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/lessons/{lesson_id}/questions", { params: { path: { lesson_id: lessonId } }, body: { body } })),
    onSuccess: async () => {
      setBody("");
      await client.invalidateQueries({ queryKey: ["lesson-questions"] });
    },
  });
  const items: Question[] = list.data ?? [];
  return (
    <div className="wo-qa">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) ask.mutate();
        }}
        className="wo-qa__ask"
      >
        <Textarea label="Ask a question about this lecture" rows={3} maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
        {ask.isError ? <Alert tone="danger" title="We could not post your question">{messageOf(ask.error)}</Alert> : null}
        <div>
          <Button type="submit" loading={ask.isPending} disabled={!body.trim()}>
            Post question
          </Button>
        </div>
      </form>
      {list.isPending ? <SkeletonRows count={2} /> : null}
      {list.isError ? <Alert tone="danger" title="We could not load the questions">{messageOf(list.error)}</Alert> : null}
      {list.isSuccess && items.length === 0 ? <EmptyState title="No questions yet">Be the first to ask.</EmptyState> : null}
      <ul className="wo-qa__list">
        {items.map((q) => (
          <li key={q.id} className="wo-qa__item">
            <p className="wo-qa__who">
              <strong>{q.mine ? "You" : q.asker}</strong> <time dateTime={q.created_at}>{timeAgo(q.created_at)}</time>
            </p>
            <p className="wo-qa__body">{q.body}</p>
            {q.answers.length > 0 ? (
              <ul className="wo-qa__answers" aria-label="Answers">
                {q.answers.map((a) => (
                  <li key={a.id} className="wo-qa__answer">
                    <p className="wo-qa__who">
                      <strong>{a.mine ? "You" : a.author}</strong>
                      {a.is_staff ? <span className="wo-qa__badge">Staff</span> : null} <time dateTime={a.created_at}>{timeAgo(a.created_at)}</time>
                    </p>
                    <p className="wo-qa__body">{a.body}</p>
                  </li>
                ))}
              </ul>
            ) : null}
            {answering === q.id ? (
              <AnswerForm questionId={q.id} onDone={() => setAnswering(null)} />
            ) : (
              <button type="button" className="wo-linkbtn" onClick={() => setAnswering(q.id)}>
                Answer
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Private notes pinned to moments in the video. Choosing a time jumps there. */
export function Notes({ lessonId, getTime, onSeek }: { lessonId: string; getTime: () => number; onSeek: (seconds: number) => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState("");
  const list = useQuery({
    queryKey: ["lesson-notes", lessonId],
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/notes", { params: { path: { lesson_id: lessonId } } })),
  });
  const add = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/lessons/{lesson_id}/notes", { params: { path: { lesson_id: lessonId } }, body: { body, seconds: Math.floor(getTime()) } })),
    onSuccess: async () => {
      setBody("");
      await client.invalidateQueries({ queryKey: ["lesson-notes"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/notes/{note_id}", { params: { path: { note_id: id } } })),
    onSuccess: async () => {
      toast.show("Note deleted");
      await client.invalidateQueries({ queryKey: ["lesson-notes"] });
    },
  });
  const notes = list.data ?? [];
  return (
    <div className="wo-qa">
      <form
        className="wo-qa__ask"
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) add.mutate();
        }}
      >
        <Textarea label="Write a note" hint="Only you can see your notes. It is saved at the moment you are watching." rows={3} maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
        {add.isError ? <Alert tone="danger" title="We could not save your note">{messageOf(add.error)}</Alert> : null}
        <div>
          <Button type="submit" loading={add.isPending} disabled={!body.trim()}>
            Add note
          </Button>
        </div>
      </form>
      {list.isSuccess && notes.length === 0 ? <EmptyState title="No notes yet">Notes you add while watching are kept here.</EmptyState> : null}
      <ul className="wo-qa__list">
        {notes.map((n) => (
          <li key={n.id} className="wo-note">
            <button type="button" className="wo-note__time" onClick={() => onSeek(n.seconds)} aria-label={`Jump to ${formatClock(n.seconds)}`}>
              {formatClock(n.seconds)}
            </button>
            <p className="wo-note__body">{n.body}</p>
            <button type="button" className="wo-note__delete" aria-label="Delete this note" onClick={() => remove.mutate(n.id)}>
              <Trash2 size={16} strokeWidth={1.5} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
