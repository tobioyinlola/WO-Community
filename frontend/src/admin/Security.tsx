import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Alert, Button, Card, Input } from "../components";
import { PageHeader, useDocumentTitle } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { mfaAgeSeconds } from "./claims";

/** Where an admin checks that two step sign in is on and can get a fresh set of recovery codes. */
export default function Security() {
  useDocumentTitle("Security");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const age = mfaAgeSeconds();
  const renew = useSubmit(async () => {
    const data = await unwrap(api.POST("/api/v1/auth/mfa/recovery-codes", { body: { code: code.trim() } }));
    setCodes(data.recovery_codes);
    setCode("");
  });
  return (
    <>
      <PageHeader eyebrow="Account" title="Security" lead="Admin accounts sign in with a password and a code from an authenticator app." />
      <div className="app-stack app-stack--lg" style={{ maxWidth: 640 }}>
        <Alert tone={age === null ? "warning" : "success"} title={age === null ? "Two step sign in is not confirmed on this session" : "Two step sign in is on"}>
          {age === null ? "Sign out and back in with your code to open the console." : "You passed the second step when you signed in."}
        </Alert>
        <Card>
          <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>Recovery codes</h2>
          <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>If you lose your phone, each code works once. Making new ones cancels the old set.</p>
          <form className="app-stack" onSubmit={(e) => { e.preventDefault(); void renew.run(); }}>
            <FormError error={renew.error} />
            <Input label="Code from your authenticator app" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
            <div><Button type="submit" variant="secondary" loading={renew.busy} disabled={code.trim().length < 6}>Make new recovery codes</Button></div>
          </form>
          {codes ? (
            <div style={{ marginTop: "var(--space-4)" }}>
              <p className="body-strong">Keep these somewhere safe. They are shown only now.</p>
              <ul style={{ margin: 0, fontFamily: "var(--font-mono)" }}>{codes.map((c) => <li key={c}>{c}</li>)}</ul>
              <div style={{ marginTop: "var(--space-3)" }}><Button variant="secondary" size="sm" onClick={() => void navigator.clipboard?.writeText(codes.join("\n"))}>Copy the codes</Button></div>
            </div>
          ) : null}
        </Card>
      </div>
    </>
  );
}
