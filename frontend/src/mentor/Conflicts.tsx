import { Link } from "react-router-dom";
import { ApiError } from "../api/errors";
import type { components } from "../api/schema";
import { Button, Modal } from "../components";
import { formatDateTime, humanise } from "../lib/format";
import { useSubmit } from "../ui/forms";

export type ConflictSession = components["schemas"]["ConflictSession"];

/** The agreed sessions a change would leave outside the schedule, when the server refused it with a 409. */
export function conflictOf(error: unknown): ConflictSession[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const sessions = (error.problem as unknown as { sessions?: ConflictSession[] }).sessions;
  return Array.isArray(sessions) && sessions.length > 0 ? sessions : null;
}

/**
 * A change would leave sessions that are already agreed outside the new schedule. Nothing is cancelled for
 * the mentor: they can keep the sessions and save, or go back and change them first.
 */
export function ConflictDialog({ sessions, onKeep, onClose }: { sessions: ConflictSession[]; onKeep: () => Promise<void>; onClose: () => void }) {
  const keep = useSubmit(async () => {
    await onKeep();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Mentorship"
      title="This change affects sessions you have agreed"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Go back
          </Button>
          <Button loading={keep.busy} onClick={() => void keep.run()}>
            Keep these sessions and save
          </Button>
        </>
      }
    >
      <div className="app-stack">
        <p className="body" style={{ margin: 0 }}>
          These sessions would fall outside your new times. Saving does not cancel or move them: they stay as booked. To change one, cancel or move it from your sessions.
        </p>
        <ul className="wo-timeoff" aria-label="Affected sessions">
          {sessions.map((s) => (
            <li key={s.id}>
              <span>
                <strong>{formatDateTime(s.starts_at)}</strong> · {s.topic} · {humanise(s.status)}
              </span>
            </li>
          ))}
        </ul>
        <Link className="wo-linkbtn" to="/app/mentors/sessions" target="_blank" rel="noreferrer">
          Open your sessions
        </Link>
      </div>
    </Modal>
  );
}
