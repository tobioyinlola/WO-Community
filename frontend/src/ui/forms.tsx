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
  // Say what is wrong and where, so a problem with a field that is not on screen can still be fixed.
  const entries = Object.entries(fields);
  return (
    <Alert tone="danger" title={entries.length === 1 ? "One answer needs fixing" : `${entries.length} answers need fixing`}>
      <ul style={{ margin: 0, paddingLeft: "1.2em" }}>
        {entries.map(([field, message]) => (
          <li key={field}>{fieldLabel(field) ? `${fieldLabel(field)}: ${message}` : message}</li>
        ))}
      </ul>
    </Alert>
  );
}

/** "profile.full_name" as "Full name"; "non_field_errors" and list positions add nothing a person needs. */
function fieldLabel(field: string): string {
  const part = field.split(".").filter((p) => !/^\d+$/.test(p) && p !== "non_field_errors").pop() ?? "";
  if (!part) return "";
  const words = part.replace(/_url$/, "").replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
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
