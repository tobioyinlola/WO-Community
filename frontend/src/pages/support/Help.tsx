import { CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { Button, Input, Textarea } from "../../components";
import { MESSAGE_MAX, MESSAGE_MIN, SUBJECT_MAX, SUBJECT_MIN } from "../../support/constants";
import { useDocumentTitle } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";

/**
 * For someone who cannot sign in, so there is no account to attach a request to. We answer by email.
 * The `website` field is for bots: people never see it, so a filled one means nobody typed it.
 */
export function HelpPage() {
  useDocumentTitle("Get help signing in");
  const [values, setValues] = useState({ name: "", email: "", subject: "", message: "", website: "" });
  const [done, setDone] = useState(false);
  const send = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/support/contact", { body: values }));
    setDone(true);
  });
  const { fields } = errorsFrom(send.error);
  const set = (patch: Partial<typeof values>) => setValues((v) => ({ ...v, ...patch }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send.run();
  };

  return (
    <div className="wo-container--narrow" style={{ margin: "var(--space-12) auto" }}>
      <div className="wo-page-rule">
        <hr />
        <span className="wo-eyebrow">Support</span>
      </div>
      <h1 className="h1" style={{ margin: "var(--space-6) 0 var(--space-3)" }}>
        Trouble signing in?
      </h1>
      <p className="body app-muted" style={{ marginBottom: "var(--space-6)" }}>
        Tell us what is happening and we will reply to your email address. If you are already signed in, use <strong>Contact support</strong> inside WO Community instead.
      </p>

      {done ? (
        <div className="wo-sent" role="status">
          <CheckCircle2 size={28} strokeWidth={1.5} aria-hidden="true" />
          <h2>We have your message</h2>
          <p>A member of the team will reply to {values.email}. Please do not reply to the confirmation email; we will write to you from the team.</p>
          <div className="wo-sent__actions">
            <Link className="wo-btn wo-btn--primary wo-btn--md" to="/login">
              Back to sign in
            </Link>
          </div>
        </div>
      ) : (
        <form className="wo-form" onSubmit={submit} noValidate>
          <Input label="Your name" autoComplete="name" value={values.name} onChange={(e) => set({ name: e.target.value })} error={fields.name} required />
          <Input label="Email we can reach you on" type="email" autoComplete="email" value={values.email} onChange={(e) => set({ email: e.target.value })} error={fields.email} required />
          <Input
            label="Subject"
            value={values.subject}
            maxLength={SUBJECT_MAX}
            onChange={(e) => set({ subject: e.target.value })}
            hint={`${SUBJECT_MIN} to ${SUBJECT_MAX} characters.`}
            error={fields.subject}
            required
          />
          <Textarea
            label="What is happening?"
            rows={6}
            value={values.message}
            maxLength={MESSAGE_MAX}
            onChange={(e) => set({ message: e.target.value })}
            hint={`${MESSAGE_MIN} to ${MESSAGE_MAX} characters. Never include your password.`}
            error={fields.message}
            required
          />
          {/* A trap for bots. Hidden from sight and from the keyboard; people leave it empty. */}
          <div className="wo-visually-hidden" aria-hidden="true">
            <label>
              Leave this empty
              <input type="text" name="website" tabIndex={-1} autoComplete="off" value={values.website} onChange={(e) => set({ website: e.target.value })} />
            </label>
          </div>
          <FormError error={send.error} listFields />
          <div>
            <Button size="lg" type="submit" loading={send.busy}>
              Send message
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
