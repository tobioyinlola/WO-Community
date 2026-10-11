import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { withPlaceholder, useCountries, useSectors, useStages } from "../../api/reference";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Alert, Button, Checkbox, Input, Select, Textarea } from "../../components";
import { useDocumentTitle } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";

const STEPS = ["Account", "About you", "Your startup", "Agree"] as const;

interface Draft {
  email: string;
  password: string;
  full_name: string;
  country: string;
  city: string;
  also_mentor: boolean;
  s_name: string;
  s_country: string;
  s_city: string;
  s_sector: string;
  s_stage: string;
  s_pitch: string;
  terms: boolean;
  privacy: boolean;
  conduct: boolean;
  marketing: boolean;
}

const EMPTY: Draft = {
  email: "",
  password: "",
  full_name: "",
  country: "",
  city: "",
  also_mentor: false,
  s_name: "",
  s_country: "",
  s_city: "",
  s_sector: "",
  s_stage: "",
  s_pitch: "",
  terms: false,
  privacy: false,
  conduct: false,
  marketing: false,
};

/** Which step each server field belongs to, so a failure takes the member back to it. */
function stepOf(field: string): number {
  if (field === "email" || field === "password") return 0;
  if (field.startsWith("profile") || field === "also_mentor") return 1;
  if (field.startsWith("startup")) return 2;
  return 3;
}

export function Register() {
  useDocumentTitle("Request access");
  const { status } = useAuth();
  const [params] = useSearchParams();
  const invitation = params.get("invite") ?? "";
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [step, setStep] = useState(0);
  const [done, setDone] = useState<"pending" | "approved" | null>(null);
  const [problems, setProblems] = useState<Record<string, string>>({});

  const countries = useCountries();
  const sectors = useSectors();
  const stages = useStages();

  // A member arriving from an invitation already has their address chosen for them.
  useEffect(() => {
    if (!invitation) return;
    void unwrap(
      api.POST("/api/v1/auth/invitations/inspect", { body: { token: invitation } }),
    )
      .then((preview) => setDraft((d) => ({ ...d, email: preview.email })))
      .catch(() => undefined);
  }, [invitation]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = useSubmit(async () => {
    const body: components["schemas"]["RegisterRequest"] = {
        email: draft.email.trim(),
        password: draft.password,
        accepted_terms: draft.terms,
        accepted_privacy: draft.privacy,
        accepted_conduct: draft.conduct,
        marketing_consent: draft.marketing,
        also_mentor: draft.also_mentor,
        invitation_token: invitation,
        profile: { full_name: draft.full_name.trim(), country: draft.country, city: draft.city.trim() },
        startup: {
          name: draft.s_name.trim(),
          country: draft.s_country || draft.country,
          city: draft.s_city.trim() || draft.city.trim(),
          sector: draft.s_sector,
          stage: draft.s_stage,
          pitch: draft.s_pitch.trim(),
        },
    };
    const { response, error } = await api.POST("/api/v1/auth/register", { body });
    if (!response.ok) {
      await unwrap(Promise.resolve({ error, response }));
      return;
    }
    setDone(response.status === 201 ? "approved" : "pending");
  });

  if (status === "authenticated") return <Navigate to="/app" replace />;

  if (done) {
    return (
      <div className="app-stack app-stack--lg">
        <div>
          <span className="wo-eyebrow">Request access</span>
          <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
            {done === "approved" ? "You are in" : "Check your email"}
          </h1>
        </div>
        {done === "approved" ? (
          <Alert tone="success" title="You are approved">
            Your invitation was accepted. Confirm your email, then sign in.
          </Alert>
        ) : (
          <Alert tone="info" title="Application received">
            We sent a link to {draft.email}. Open it to confirm your address; an admin will then review
            your application and email you.
          </Alert>
        )}
        <Link className="wo-btn wo-btn--primary wo-btn--lg" to="/login">
          Go to sign in
        </Link>
      </div>
    );
  }

  const here = errorsFrom(submit.error).fields;
  const err = (...names: string[]) => names.map((n) => here[n]).find(Boolean) ?? problems[names[0] ?? ""];

  /** Checks the step in front of the member before moving on, so mistakes are caught close to home. */
  const validate = (index: number): Record<string, string> => {
    const out: Record<string, string> = {};
    if (index === 0) {
      if (!/^\S+@\S+\.\S+$/.test(draft.email.trim())) out.email = "Enter a full email address.";
      if (draft.password.length < 10) out.password = "Use at least 10 characters.";
    } else if (index === 1) {
      if (draft.full_name.trim().length < 2) out["profile.full_name"] = "Enter your full name.";
      if (!draft.country) out["profile.country"] = "Choose your country.";
      if (!draft.city.trim()) out["profile.city"] = "Enter your city.";
    } else if (index === 2) {
      if (!draft.s_name.trim()) out["startup.name"] = "Enter the name.";
      if (!draft.s_sector) out["startup.sector"] = "Choose a sector.";
      if (!draft.s_stage) out["startup.stage"] = "Choose a stage.";
      if (!draft.s_pitch.trim()) out["startup.pitch"] = "Describe it in a sentence.";
    } else {
      if (!draft.terms) out.accepted_terms = "Accept the terms to continue.";
      if (!draft.privacy) out.accepted_privacy = "Accept the privacy policy to continue.";
      if (!draft.conduct) out.accepted_conduct = "Accept the code of conduct to continue.";
    }
    return out;
  };

  const next = async (event: FormEvent) => {
    event.preventDefault();
    const found = validate(step);
    setProblems(found);
    if (Object.keys(found).length) return;
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    await submit.run();
  };

  // If the server rejects something from an earlier step, go back to it.
  if (submit.error && Object.keys(here).length) {
    const earliest = Math.min(...Object.keys(here).map(stepOf));
    if (earliest < step) setStep(earliest);
  }

  return (
    <form onSubmit={next} noValidate className="app-stack app-stack--lg">
      <div>
        <span className="wo-eyebrow">Request access</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>
          Join the community
        </h1>
        <p className="body app-muted" style={{ margin: 0 }}>
          It takes about two minutes. An admin reviews every application.
        </p>
      </div>
      <ol className="app-steps" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li key={label} aria-current={i === step ? "step" : undefined} data-done={i < step}>
            {label}
          </li>
        ))}
      </ol>
      <FormError error={submit.error} />

      {step === 0 ? (
        <>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            value={draft.email}
            readOnly={Boolean(invitation) && Boolean(draft.email)}
            onChange={(e) => set("email", e.target.value)}
            error={err("email")}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            hint="At least 10 characters. A passphrase of a few words works well."
            value={draft.password}
            onChange={(e) => set("password", e.target.value)}
            error={err("password")}
          />
        </>
      ) : null}

      {step === 1 ? (
        <>
          <Input
            label="Full name"
            autoComplete="name"
            value={draft.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            error={err("profile.full_name")}
          />
          <div className="app-formgrid">
            <Select
              label="Country"
              options={withPlaceholder(countries.data)}
              value={draft.country}
              onChange={(e) => set("country", e.target.value)}
              error={err("profile.country")}
            />
            <Input
              label="City"
              autoComplete="address-level2"
              value={draft.city}
              onChange={(e) => set("city", e.target.value)}
              error={err("profile.city")}
            />
          </div>
          <Checkbox
            label="I am also interested in mentoring other founders"
            checked={draft.also_mentor}
            onChange={(e) => set("also_mentor", e.target.checked)}
          />
        </>
      ) : null}

      {step === 2 ? (
        <>
          <Input
            label="Startup name"
            value={draft.s_name}
            onChange={(e) => set("s_name", e.target.value)}
            error={err("startup.name")}
          />
          <div className="app-formgrid">
            <Select
              label="Sector"
              options={withPlaceholder(sectors.data)}
              value={draft.s_sector}
              onChange={(e) => set("s_sector", e.target.value)}
              error={err("startup.sector")}
            />
            <Select
              label="Stage"
              options={withPlaceholder(stages.data)}
              value={draft.s_stage}
              onChange={(e) => set("s_stage", e.target.value)}
              error={err("startup.stage")}
            />
          </div>
          <Textarea
            label="What does it do?"
            hint="One sentence, up to 160 characters."
            maxLength={160}
            rows={3}
            value={draft.s_pitch}
            onChange={(e) => set("s_pitch", e.target.value)}
            error={err("startup.pitch")}
          />
        </>
      ) : null}

      {step === 3 ? (
        <div className="app-stack">
          <Checkbox
            label={
              <span>
                I accept the{" "}
                <Link className="app-link" to="/legal/terms" target="_blank">
                  terms
                </Link>
              </span>
            }
            checked={draft.terms}
            onChange={(e) => set("terms", e.target.checked)}
          />
          {err("accepted_terms") ? <span className="wo-error">! {err("accepted_terms")}</span> : null}
          <Checkbox
            label={
              <span>
                I accept the{" "}
                <Link className="app-link" to="/legal/privacy" target="_blank">
                  privacy policy
                </Link>
              </span>
            }
            checked={draft.privacy}
            onChange={(e) => set("privacy", e.target.checked)}
          />
          {err("accepted_privacy") ? <span className="wo-error">! {err("accepted_privacy")}</span> : null}
          <Checkbox
            label={
              <span>
                I will follow the{" "}
                <Link className="app-link" to="/legal/conduct" target="_blank">
                  code of conduct
                </Link>
              </span>
            }
            checked={draft.conduct}
            onChange={(e) => set("conduct", e.target.checked)}
          />
          {err("accepted_conduct") ? <span className="wo-error">! {err("accepted_conduct")}</span> : null}
          <Checkbox
            label="Send me community news now and then (optional)"
            checked={draft.marketing}
            onChange={(e) => set("marketing", e.target.checked)}
          />
        </div>
      ) : null}

      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        {step > 0 ? (
          <Button variant="ghost" onClick={() => setStep(step - 1)}>
            Back
          </Button>
        ) : (
          <span />
        )}
        <Button size="lg" type="submit" loading={submit.busy}>
          {step === STEPS.length - 1 ? "Request access" : "Continue"}
        </Button>
      </div>
      <p className="body-sm app-muted" style={{ margin: 0 }}>
        Already a member?{" "}
        <Link className="app-link" to="/login">
          Sign in
        </Link>
      </p>
    </form>
  );
}
