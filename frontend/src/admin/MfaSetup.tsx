import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { setAccessToken } from "../api/session";
import { Alert, Button, Card, Input } from "../components";
import { PageHeader, useDocumentTitle } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";

/**
 * Admin accounts need a second step. This walks through adding an authenticator app, then shows the
 * recovery codes once. Until it is done the rest of the console stays closed.
 */
export default function MfaSetup({ onDone, onConfirmed }: { onDone: () => void; onConfirmed: () => void }) {
  useDocumentTitle("Set up two step sign in");
  const [setup, setSetup] = useState<{ secret: string; uri: string; image: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  const start = useSubmit(async () => {
    const data = await unwrap(api.POST("/api/v1/auth/mfa/enrol"));
    setSetup({ secret: data.secret, uri: data.otpauth_uri, image: await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 192 }) });
  });
  const confirm = useSubmit(async () => {
    const data = await unwrap(api.POST("/api/v1/auth/mfa/confirm", { body: { code: code.trim() } }));
    // Keep this screen open while the codes are shown, even though the session now counts as verified.
    onConfirmed();
    setAccessToken(data.access_token);
    setCodes(data.recovery_codes);
  });

  const asked = useRef(false);
  useEffect(() => {
    // Each request replaces the key, so ask once even when the effect runs twice in development.
    if (asked.current) return;
    asked.current = true;
    void start.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (codes) {
    return (
      <>
        <PageHeader eyebrow="Security" title="Keep these recovery codes" lead="Each works once if you lose your phone. They are shown only now." />
        <Card>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, fontFamily: "var(--font-mono)" }}>
            {codes.map((c) => <li key={c}>{c}</li>)}
          </ul>
          <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
            <Button variant="secondary" onClick={() => void navigator.clipboard?.writeText(codes.join("\n"))}>Copy the codes</Button>
            <Button onClick={onDone}>I have saved them</Button>
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Security" title="Set up two step sign in" lead="Admin accounts need a code from an authenticator app each time they sign in." />
      <Card>
        <div className="app-stack">
          <FormError error={start.error ?? confirm.error} />
          {setup ? (
            <>
              <ol className="app-stack" style={{ margin: 0, paddingLeft: "var(--space-6)" }}>
                <li>Open an authenticator app (for example Google Authenticator, 1Password or Authy).</li>
                <li>Scan this code, or type the key below by hand.</li>
                <li>Enter the 6 digit code the app shows.</li>
              </ol>
              <div className="app-cluster" style={{ alignItems: "center" }}>
                <img src={setup.image} width={192} height={192} alt="QR code for your authenticator app" style={{ background: "white", borderRadius: "var(--radius-md)" }} />
                <div>
                  <p className="caption app-muted" style={{ margin: 0 }}>Setup key</p>
                  <code style={{ overflowWrap: "anywhere" }}>{setup.secret}</code>
                </div>
              </div>
              <form className="app-stack" onSubmit={(e) => { e.preventDefault(); void confirm.run(); }}>
                <Input label="Code from the app" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
                <div><Button type="submit" loading={confirm.busy} disabled={code.trim().length < 6}>Turn on two step sign in</Button></div>
              </form>
            </>
          ) : start.busy ? <p className="body app-muted" role="status">Preparing…</p> : (
            <Alert tone="info" title="Could not start" action={<Button size="sm" variant="secondary" onClick={() => void start.run()}>Try again</Button>}>Try again in a moment.</Alert>
          )}
        </div>
      </Card>
    </>
  );
}
