import { useState, type ReactNode } from "react";
import { Button, Modal, Textarea } from "../components";
import { FormError, useSubmit } from "../ui/forms";

/** Asks for a reason (members are told why) and runs the action with it. */
export function ReasonDialog({
  title,
  confirmLabel,
  tone = "primary",
  intro,
  required = true,
  onConfirm,
  onClose,
}: {
  title: string;
  confirmLabel: string;
  tone?: "primary" | "danger";
  intro?: ReactNode;
  required?: boolean;
  onConfirm: (reason: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const submit = useSubmit(async () => {
    await onConfirm(reason.trim());
    onClose();
  });
  const ready = !required || reason.trim().length > 0;
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title={title}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={submit.busy} disabled={!ready} onClick={() => void submit.run()}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="app-stack">
        {intro ? <p className="body" style={{ margin: 0 }}>{intro}</p> : null}
        <FormError error={submit.error} listFields />
        <Textarea label={required ? "Reason" : "Note (optional)"} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} hint="This is kept in the audit log." />
      </div>
    </Modal>
  );
}

/** A plain yes or no for an action that needs no reason. */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  tone = "primary",
  onConfirm,
  onClose,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}) {
  const submit = useSubmit(async () => {
    await onConfirm();
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title={title}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={submit.busy} onClick={() => void submit.run()}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} listFields />
        <p className="body" style={{ margin: 0 }}>{body}</p>
      </div>
    </Modal>
  );
}
