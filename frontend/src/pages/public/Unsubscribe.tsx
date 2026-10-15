import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { Alert, Button } from "../../components";
import { useDocumentTitle } from "../../ui/blocks";

/** Opened from the unsubscribe link in announcement emails. It asks first, because mail
 * scanners open links on their own and must not unsubscribe anyone. */
export function Unsubscribe() {
  useDocumentTitle("Unsubscribe");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"ask" | "working" | "done" | "failed">(token ? "ask" : "failed");
  const [message, setMessage] = useState("");

  const confirm = () => {
    setState("working");
    void unwrap(api.POST("/api/v1/unsubscribe", { body: { token } }))
      .then(() => setState("done"))
      .catch((error: unknown) => {
        setMessage(messageOf(error));
        setState("failed");
      });
  };

  return (
    <div className="app-stack app-stack--lg" style={{ maxWidth: 560, margin: "0 auto", padding: "var(--space-6) var(--space-4)" }}>
      <h1 className="h1" style={{ margin: 0 }}>
        Unsubscribe from announcements
      </h1>
      {state === "ask" || state === "working" ? (
        <>
          <p className="body">
            You'll stop getting news and announcement emails from WO Community. Emails about your account,
            like password resets and approvals, still arrive.
          </p>
          <div>
            <Button variant="primary" onClick={confirm} disabled={state === "working"}>
              {state === "working" ? "Unsubscribing…" : "Unsubscribe"}
            </Button>
          </div>
        </>
      ) : null}
      {state === "done" ? (
        <Alert tone="success" title="You're unsubscribed">
          You won't get announcement emails any more. You can turn them back on in your settings at any time.
        </Alert>
      ) : null}
      {state === "failed" ? (
        <Alert tone="danger" title="This link did not work">
          {message || "It may be incomplete."} Sign in and change which emails you get in Settings.
        </Alert>
      ) : null}
      <p className="body">
        <Link className="app-link" to="/login">
          Sign in to WO Community
        </Link>
      </p>
    </div>
  );
}
