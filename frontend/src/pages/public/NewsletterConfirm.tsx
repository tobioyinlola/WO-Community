import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { Alert } from "../../components";
import { useDocumentTitle } from "../../ui/blocks";

/** Opened from the link in the newsletter confirmation email. */
export function NewsletterConfirm() {
  useDocumentTitle("Confirm your subscription");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const [message, setMessage] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    void unwrap(api.POST("/api/v1/newsletter/confirm", { body: { token } }))
      .then(() => setState("done"))
      .catch((error: unknown) => {
        setMessage(messageOf(error));
        setState("failed");
      });
  }, [token]);

  return (
    <div className="app-stack app-stack--lg" style={{ maxWidth: 560, margin: "0 auto", padding: "var(--space-12) var(--space-4)" }}>
      <div>
        <span className="wo-eyebrow">Newsletter</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0 0" }}>
          {state === "done" ? "You're subscribed" : "Confirm your subscription"}
        </h1>
      </div>
      {state === "working" ? <p className="body">Checking your link&hellip;</p> : null}
      {state === "done" ? (
        <>
          <Alert tone="success" title="Thank you">
            You&rsquo;ll get the WO Community newsletter. Every issue has a link to leave if you change your mind.
          </Alert>
          <p className="body">
            Building something?{" "}
            <Link className="app-link" to="/register">
              Request access to the community
            </Link>
            .
          </p>
        </>
      ) : null}
      {state === "failed" ? (
        <Alert tone="danger" title="This link did not work">
          {message || "It may have expired."} Sign up again at the bottom of any page and we&rsquo;ll send a new link.
        </Alert>
      ) : null}
    </div>
  );
}
