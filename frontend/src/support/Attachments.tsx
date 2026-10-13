import { Paperclip, X } from "lucide-react";
import { useRef, useState, type ChangeEvent } from "react";
import { Button } from "../components";
import { ATTACHMENT_LIMIT, checkAttachment, uploadFile, type Uploaded } from "../api/upload";

interface Item extends Partial<Uploaded> {
  key: string;
  name: string;
  state: "uploading" | "ready";
}

export interface AttachmentState {
  items: Item[];
  ids: string[];
  busy: boolean;
  problem: string;
  add: (files: FileList | File[]) => Promise<void>;
  remove: (key: string) => void;
  reset: () => void;
}

/** Files chosen for a message. Each is checked, then uploaded straight away so sending is quick. */
export function useAttachments(): AttachmentState {
  const [items, setItems] = useState<Item[]>([]);
  const [problem, setProblem] = useState("");
  const counter = useRef(0);

  const add = async (files: FileList | File[]) => {
    setProblem("");
    const chosen = Array.from(files);
    const room = ATTACHMENT_LIMIT - items.length;
    if (chosen.length > room) setProblem(room <= 0 ? `You can attach up to ${ATTACHMENT_LIMIT} files.` : `Only ${room} more ${room === 1 ? "file fits" : "files fit"}.`);
    for (const file of chosen.slice(0, Math.max(0, room))) {
      const wrong = checkAttachment(file);
      if (wrong) {
        setProblem(wrong);
        continue;
      }
      counter.current += 1;
      const key = `f${counter.current}`;
      setItems((current) => [...current, { key, name: file.name, state: "uploading" }]);
      try {
        const done = await uploadFile(file, "support_attachment");
        setItems((current) => current.map((i) => (i.key === key ? { ...i, ...done, state: "ready" } : i)));
      } catch (error) {
        setItems((current) => current.filter((i) => i.key !== key));
        setProblem(error instanceof Error ? error.message : "We could not upload that file.");
      }
    }
  };

  return {
    items,
    ids: items.filter((i) => i.state === "ready" && i.id).map((i) => i.id as string),
    busy: items.some((i) => i.state === "uploading"),
    problem,
    add,
    remove: (key) => setItems((current) => current.filter((i) => i.key !== key)),
    reset: () => {
      setItems([]);
      setProblem("");
    },
  };
}

/** The attach button and the list of chosen files. */
export function Attachments({ state, label = "Attach files" }: { state: AttachmentState; label?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.length) void state.add(event.target.files);
    event.target.value = "";
  };
  const full = state.items.length >= ATTACHMENT_LIMIT;
  return (
    <div className="wo-attach">
      <input ref={input} type="file" hidden multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={onPick} aria-label={label} tabIndex={-1} />
      <div className="wo-attach__bar">
        <Button variant="secondary" size="sm" icon={<Paperclip size={16} strokeWidth={1.5} />} disabled={full} onClick={() => input.current?.click()}>
          {label}
        </Button>
        <span className="wo-attach__hint">Up to {ATTACHMENT_LIMIT} files, PDF or image, 5 MB each.</span>
      </div>
      {state.items.length > 0 ? (
        <ul className="wo-attach__list" aria-label="Attached files">
          {state.items.map((item) => (
            <li key={item.key} className="wo-attach__item">
              <Paperclip size={16} strokeWidth={1.5} aria-hidden="true" />
              <span className="wo-attach__name">{item.name}</span>
              <span className="wo-attach__state" role="status">
                {item.state === "uploading" ? "Uploading…" : "Ready"}
              </span>
              <button type="button" className="wo-attach__remove" aria-label={`Remove ${item.name}`} onClick={() => state.remove(item.key)}>
                <X size={16} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {state.problem ? (
        <p className="wo-attach__problem" role="alert">
          {state.problem}
        </p>
      ) : null}
    </div>
  );
}
