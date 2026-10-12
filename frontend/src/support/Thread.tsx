import { LockKeyhole, Paperclip } from "lucide-react";
import { useState } from "react";
import { Avatar } from "../components";
import { formatDateTime, timeAgo } from "../lib/format";
import { RichText } from "../ui/blocks";
import "../styles/shared-ui.css";

export interface ThreadMessage {
  id: string;
  body: string;
  is_internal: boolean;
  created_at: string;
  author: { id: string | null; name: string; is_support: boolean; avatar: { [key: string]: string } | null };
  attachments: Array<{ id: string; filename: string; size: number; content_type: string }>;
}

function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * The conversation on a request: who wrote what and when, with files. An internal note is set apart
 * by its background and a label, since only admins ever see it.
 */
export function Thread({ messages, fetchLink }: { messages: ThreadMessage[]; fetchLink: (attachmentId: string) => Promise<string> }) {
  const [problem, setProblem] = useState("");
  const open = async (id: string) => {
    setProblem("");
    try {
      window.open(await fetchLink(id), "_blank", "noopener,noreferrer");
    } catch {
      setProblem("We could not open that file. Try again.");
    }
  };
  return (
    <ol className="wo-thread" aria-label="Conversation">
      {messages.map((m) => (
        <li key={m.id} className="wo-thread__item" data-support={m.author.is_support} data-internal={m.is_internal}>
          <Avatar name={m.author.name} id={m.author.id ?? undefined} src={m.author.avatar?.thumb} size="sm" />
          <div className="wo-thread__card">
            <header className="wo-thread__head">
              <strong>{m.author.name}</strong>
              {m.author.is_support ? <span className="wo-thread__tag">Support</span> : null}
              {m.is_internal ? (
                <span className="wo-thread__tag wo-thread__tag--note">
                  <LockKeyhole size={12} strokeWidth={1.5} aria-hidden="true" /> Internal note
                </span>
              ) : null}
              <time dateTime={m.created_at} title={formatDateTime(m.created_at)}>
                {timeAgo(m.created_at)}
              </time>
            </header>
            <RichText html={m.body} />
            {m.attachments.length > 0 ? (
              <ul className="wo-thread__files" aria-label="Attachments">
                {m.attachments.map((a) => (
                  <li key={a.id}>
                    <button type="button" className="wo-linkbtn" onClick={() => void open(a.id)}>
                      <Paperclip size={14} strokeWidth={1.5} aria-hidden="true" /> {a.filename}
                    </button>
                    <span className="wo-thread__size"> {size(a.size)}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </li>
      ))}
      {problem ? (
        <li role="alert" className="wo-attach__problem">
          {problem}
        </li>
      ) : null}
    </ol>
  );
}
