import { useState } from "react";
import { Alert } from "../components";
import { ApiError, messageOf } from "../api/errors";

/** Field messages from a failed save, and a sentence for whatever is not about one field. */
export function errorsFrom(error: unknown): { fields: Record<string, string>; general: string } {
  if (error instanceof ApiError && error.isValidation) {
    const fields = error.fieldErrors;
    return { fields, general: Object.keys(fields).length ? "" : error.message };
  }
  return { fields: {}, general: error ? messageOf(error) : "" };
}

/** Shows the general part of a failure, if there is one. Field messages sit beside their fields. */
export function FormError({ error, listFields = false }: { error: unknown; listFields?: boolean }) {
  const { fields, general } = errorsFrom(error);
  if (!error) return null;
  // Where there are no fields to mark (a dialog), say what the server said instead of pointing at nothing.
  if (listFields && !general && Object.keys(fields).length > 0) {
    return (
      <Alert tone="danger" title="That did not work">
        {Object.values(fields).join(" ")}
      </Alert>
    );
  }
  if (general) {
    return (
      <Alert tone="danger" title="That did not work">
        {general}
      </Alert>
    );
  }
  const count = Object.keys(fields).length;
  return (
    <Alert tone="danger" title="Check the highlighted fields">
      {count === 1 ? "One field needs attention." : `${count} fields need attention.`}
    </Alert>
  );
}

/** Runs an async submit, tracking whether it is busy and what went wrong. */
export function useSubmit<A extends unknown[], R>(action: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async (...args: A): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await action(...args);
    } catch (caught) {
      setError(caught);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { run, busy, error, setError };
}
