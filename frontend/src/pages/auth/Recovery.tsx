import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { Alert, Button, Input } from "../../components";
import { useDocumentTitle } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";

/** Opened from the link in the registration email. */
export function VerifyEmail() {
  useDocumentTitle("Confirm your email");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const [message, setMessage] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    void unwrap(api.POST("/api/v1/auth/verify-email", { body: { token } }))
      .then(() => setState("done"))
      .catch((error: unknown) => {
        setMessage(messageOf(error));
        setState("failed");
      });
  }, [token]);

  return (
    <div className="app-stack app-stack--lg">
      <div>
        <span className="wo-eyebrow">Membership</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
          Confirm your email
        </h1>
      </div>
      {state === "working" ? <p className="body">Checking your link&hellip;</p> : null}
      {state === "done" ? (
        <>
          <Alert tone="success" title="Email confirmed">
            Thank you. Sign in to see where your application stands.
          </Alert>
          <Link className="wo-btn wo-btn--primary wo-btn--lg" to="/login">
            Sign in
          </Link>
        </>
      ) : null}
      {state === "failed" ? (
        <Alert tone="danger" title="This link did not work">
          {message || "It may have expired or already been used."} Register again or ask for a new link.
        </Alert>
      ) : null}
    </div>
  );
}

export function ForgotPassword() {
  useDocumentTitle("Reset your password");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const submit = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/auth/password/forgot", { body: { email: email.trim() } }));
    setSent(true);
  });

  if (sent) {
    return (
      <div className="app-stack app-stack--lg">
        <h1 className="h1" style={{ margin: 0 }}>
          Check your email
        </h1>
        <Alert tone="info" title="If that address has an account">
          we have sent a link to choose a new password. It works for a short time only.
        </Alert>
        <Link className="app-link" to="/login">
          Back to sign in
        </Link>
      </div>
    );
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit.run();
  };
  return (
    <form onSubmit={onSubmit} noValidate className="app-stack app-stack--lg">
      <div>
        <span className="wo-eyebrow">Members</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
          Reset your password
        </h1>
        <p className="body app-muted" style={{ margin: 0 }}>
          Enter your email and we will send you a link.
        </p>
      </div>
      <FormError error={submit.error} />
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={errorsFrom(submit.error).fields.email}
      />
      <Button size="lg" type="submit" loading={submit.busy} disabled={!email.trim()}>
        Send the link
      </Button>
      <Link className="app-link" to="/login">
        Back to sign in
      </Link>
    </form>
  );
}

export function ResetPassword() {
  useDocumentTitle("Choose a new password");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [mismatch, setMismatch] = useState("");
  const submit = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/auth/password/reset", { body: { token, password } }));
    navigate("/login", { replace: true });
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (password !== again) {
      setMismatch("The two passwords are different.");
      return;
    }
    setMismatch("");
    void submit.run();
  };

  if (!token) {
    return (
      <Alert tone="danger" title="This link is incomplete">
        Ask for a new one from the sign in page.
      </Alert>
    );
  }
  return (
    <form onSubmit={onSubmit} noValidate className="app-stack app-stack--lg">
      <div>
        <span className="wo-eyebrow">Members</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
          Choose a new password
        </h1>
      </div>
      <FormError error={submit.error} />
      <Input
        label="New password"
        type="password"
        autoComplete="new-password"
        hint="At least 10 characters."
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={errorsFrom(submit.error).fields.password}
      />
      <Input
        label="Type it again"
        type="password"
        autoComplete="new-password"
        value={again}
        onChange={(e) => setAgain(e.target.value)}
        error={mismatch}
      />
      <Button size="lg" type="submit" loading={submit.busy} disabled={!password || !again}>
        Save password
      </Button>
    </form>
  );
}
