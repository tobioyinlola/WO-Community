import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { isAdmin } from "../../admin/permissions";
import { ApiError } from "../../api/errors";
import { useAuth } from "../../auth/AuthProvider";
import { wasSignedOutIdle } from "../../auth/idle";
import { Alert, Button, Input } from "../../components";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useDocumentTitle } from "../../ui/blocks";

interface LocationState {
  from?: string;
}

export function Login() {
  useDocumentTitle("Sign in");
  const { status, me, login, verifyMfa } = useAuth();
  const location = useLocation();
  // Where to go once signed in: back to the page that asked for it, or else the person's own
  // home, which for an admin is the admin dashboard.
  const asked = (location.state as LocationState | null)?.from;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [idleNote] = useState(wasSignedOutIdle);
  const [code, setCode] = useState("");

  const signIn = useSubmit(async () => {
    const outcome = await login(email.trim(), password);
    if (outcome.kind === "mfa") setMfaToken(outcome.mfaToken);
    // Signed in: the redirect below takes over once the account has loaded.
  });
  const confirm = useSubmit(async () => {
    if (!mfaToken) return;
    await verifyMfa(mfaToken, code.trim());
  });

  if (status === "authenticated" && me) {
    const home = isAdmin(me.roles ?? []) ? "/admin" : "/app";
    return <Navigate to={asked && asked !== "/app" ? asked : home} replace />;
  }

  const unverified = signIn.error instanceof ApiError && signIn.error.code === "email_not_verified";

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void (mfaToken ? confirm.run() : signIn.run());
  };

  if (mfaToken) {
    return (
      <form onSubmit={onSubmit} noValidate className="app-stack app-stack--lg">
        <div>
          <span className="wo-eyebrow">Two step check</span>
          <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
            Enter your code
          </h1>
          <p className="body app-muted" style={{ margin: 0 }}>
            Open your authenticator app and type the 6 digit code, or use a recovery code.
          </p>
        </div>
        <FormError error={confirm.error} />
        <Input
          label="Code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          error={errorsFrom(confirm.error).fields.code}
        />
        <Button size="lg" type="submit" loading={confirm.busy} disabled={!code.trim()}>
          Confirm
        </Button>
        <Button variant="ghost" onClick={() => setMfaToken(null)}>
          Back to sign in
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="app-stack app-stack--lg">
      <div>
        <span className="wo-eyebrow">Members</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
          Sign in
        </h1>
        <p className="body app-muted" style={{ margin: 0 }}>
          Welcome back. Pick up where you left off.
        </p>
      </div>
      {idleNote && !signIn.error ? (
        <Alert tone="info" title="You were signed out">
          For your security, we sign you out after 5 minutes without activity. Sign in again to continue.
        </Alert>
      ) : null}
      {unverified ? (
        <Alert tone="warning" title="Confirm your email first">
          We sent you a link when you registered. Open it, then sign in.
        </Alert>
      ) : (
        <FormError error={signIn.error} />
      )}
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={errorsFrom(signIn.error).fields.email}
      />
      <Input
        label="Password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={errorsFrom(signIn.error).fields.password}
      />
      <Button size="lg" type="submit" loading={signIn.busy} disabled={!email.trim() || !password}>
        Sign in
      </Button>
      <p className="body-sm" style={{ margin: 0 }}>
        <Link className="app-link" to="/forgot-password">
          Forgot your password?
        </Link>{" "}
        <Link className="app-link" to="/help">
          Contact support
        </Link>
      </p>
      <hr className="app-divider" style={{ margin: 0 }} />
      <p className="body app-muted" style={{ margin: 0 }}>
        New here?{" "}
        <Link className="app-link" to="/register">
          Request access
        </Link>
      </p>
    </form>
  );
}
