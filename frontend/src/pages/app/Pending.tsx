import { Link } from "react-router-dom";
import { Alert } from "../../components";
import { useDocumentTitle } from "../../ui/blocks";

/** What a member sees until an admin approves them: the status, the next step, nothing else. */
export function PendingNotice() {
  useDocumentTitle("Application received");
  return (
    <div className="wo-container--narrow" style={{ margin: "var(--space-12) auto" }}>
      <div className="wo-page-rule">
        <hr />
        <span className="wo-eyebrow">Membership</span>
      </div>
      <h1 className="h1" style={{ margin: "var(--space-6) 0 var(--space-4)" }}>
        Thank you for applying
      </h1>
      <Alert tone="info" title="Application received">
        An admin will review it and email you. Once you are approved, the whole community opens up.
      </Alert>
      <p className="body app-muted" style={{ marginTop: "var(--space-6)" }}>
        While you wait, you can make your{" "}
        <Link className="app-link" to="/app/me">
          profile
        </Link>{" "}
        ready so people know who you are on day one.
      </p>
    </div>
  );
}
