import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useAuth } from "../auth/AuthProvider";
import { Button, Input, Select, Textarea } from "../components";
import { Drawer } from "../ui/Drawer";
import { Attachments, useAttachments } from "./Attachments";
import { CATEGORIES, MESSAGE_MAX, MESSAGE_MIN, SUBJECT_MAX, SUBJECT_MIN } from "./constants";

interface SupportContext {
  /** Opens the "Contact support" drawer, optionally with a category already chosen. */
  open: (category?: string) => void;
}

const Context = createContext<SupportContext>({ open: () => undefined });

/** Where the rest of the app asks for the support drawer, so "Contact support" is one thing everywhere. */
export const useSupport = () => useContext(Context);

interface Sent {
  id: string;
  reference: string;
}

interface FormState {
  sent: boolean;
  busy: boolean;
}

function SupportForm({
  category,
  onDone,
  onDirty,
  onState,
}: {
  category: string;
  onDone: () => void;
  onDirty: (dirty: boolean) => void;
  onState: (state: FormState) => void;
}) {
  const { me } = useAuth();
  const client = useQueryClient();
  const profile = useQuery({ queryKey: ["me", "profile"], queryFn: () => unwrap(api.GET("/api/v1/me/profile")) });
  const name = profile.data?.full_name || me?.email || "";
  const [values, setValues] = useState({ category, subject: "", message: "" });
  const [sent, setSent] = useState<Sent | null>(null);
  const files = useAttachments();
  // One key for this form, so a double click or a retry opens a single request.
  const key = useRef(crypto.randomUUID());

  const change = (patch: Partial<typeof values>) => {
    const next = { ...values, ...patch };
    setValues(next);
    onDirty(next.subject !== "" || next.message !== "");
  };

  const send = useSubmit(async () => {
    const created = await unwrap(
      api.POST("/api/v1/support/tickets", {
        params: { header: { "Idempotency-Key": key.current } },
        body: { category: values.category as never, subject: values.subject, message: values.message, attachments: files.ids },
      }),
    );
    setSent({ id: created.id, reference: created.reference });
    onDirty(false);
    void client.invalidateQueries({ queryKey: ["support"] });
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send.run();
  };

  const { fields } = errorsFrom(send.error);
  const busy = files.busy || send.busy;
  useEffect(() => onState({ sent: sent !== null, busy }), [sent, busy, onState]);

  if (sent) {
    return (
      <div className="wo-sent" role="status">
        <CheckCircle2 size={28} strokeWidth={1.5} aria-hidden="true" />
        <h3>We have your request</h3>
        <p>
          Your reference is <strong>{sent.reference}</strong>. We will reply here in the app and by email.
        </p>
        <div className="wo-sent__actions">
          <Link className="wo-btn wo-btn--primary wo-btn--md" to={`/app/support/${sent.id}`} onClick={onDone}>
            View request
          </Link>
          <Button variant="secondary" onClick={onDone}>
            Close
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form id="support-form" className="wo-form" onSubmit={submit} noValidate>
      <p className="wo-form__who">
        Sending as <strong>{name}</strong>
        {me?.email && name !== me.email ? <> ({me.email})</> : null}
      </p>
      <Select label="Category" value={values.category} onChange={(e) => change({ category: e.target.value })} options={CATEGORIES} error={fields.category} />
      <Input
        label="Subject"
        value={values.subject}
        maxLength={SUBJECT_MAX}
        onChange={(e) => change({ subject: e.target.value })}
        hint={`${SUBJECT_MIN} to ${SUBJECT_MAX} characters.`}
        error={fields.subject}
        required
      />
      <Textarea
        label="Message"
        rows={7}
        value={values.message}
        maxLength={MESSAGE_MAX}
        onChange={(e) => change({ message: e.target.value })}
        hint={`What happened, and what you expected. ${MESSAGE_MIN} to ${MESSAGE_MAX} characters (${values.message.length} so far).`}
        error={fields.message}
        required
      />
      <Attachments state={files} />
      <FormError error={send.error} listFields />
    </form>
  );
}

/** Holds the drawer and the way to open it, for the member area. */
export function SupportProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("other");
  const [dirty, setDirty] = useState(false);
  // A new key for every opening, so each visit starts a clean form.
  const [round, setRound] = useState(0);
  const [state, setState] = useState<FormState>({ sent: false, busy: false });

  const show = useCallback((initial?: string) => {
    setCategory(initial ?? "other");
    setRound((r) => r + 1);
    setDirty(false);
    setState({ sent: false, busy: false });
    setOpen(true);
  }, []);
  const value = useMemo(() => ({ open: show }), [show]);

  return (
    <Context.Provider value={value}>
      {children}
      <Drawer
        open={open}
        onOpenChange={setOpen}
        eyebrow="Support"
        title="Contact support"
        subtitle="Tell us what is wrong and we will help."
        dirty={dirty}
        footer={
          state.sent ? null : (
            <>
              <Button variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <SubmitButton busy={state.busy} />
            </>
          )
        }
      >
        <SupportForm key={round} category={category} onDone={() => setOpen(false)} onDirty={setDirty} onState={setState} />
      </Drawer>
    </Context.Provider>
  );
}

/** The submit button lives in the drawer footer, so it points at the form by id. */
function SubmitButton({ busy }: { busy: boolean }) {
  return (
    <Button type="submit" form="support-form" loading={busy}>
      Send request
    </Button>
  );
}
