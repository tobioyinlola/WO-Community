import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { useAuth } from "../../auth/AuthProvider";
import { Alert, Button, Input } from "../../components";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useDocumentTitle } from "../../ui/blocks";

interface LocationState {
  from?: string;
}

export function Login() {
  useDocumentTitle("Sign in");
  const { status, login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState | null)?.from ?? "/app";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const signIn = useSubmit(async () => {
    const outcome = await login(email.trim(), password);
    if (outcome.kind === "mfa") setMfaToken(outcome.mfaToken);
    else navigate(from, { replace: true });
  });
  const confirm = useSubmit(async () => {
    if (!mfaToken) return;
    await verifyMfa(mfaToken, code.trim());
    navigate(from, { replace: true });
  });

  if (status === "authenticated") return <Navigate to={from} replace />;

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
