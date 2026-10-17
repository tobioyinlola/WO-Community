import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { withPlaceholder, useCountries, useSectors, useStages } from "../../api/reference";
import { api, unwrap } from "../../api/client";
import { FriendlyError } from "../../api/errors";
import type { components } from "../../api/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Alert, Button, Checkbox, Input, Select, Textarea } from "../../components";
import { isAdmin } from "../../admin/permissions";
import { EMPTY_REFERRAL, ReferralFields, referralBody, type ReferralDraft } from "../../referrals/ReferralFields";
import { rememberRefCode, storedRefCode } from "../../referrals/ref";
import { useDocumentTitle } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";

const STEPS = ["Account", "About you", "Your company", "Agree"] as const;

interface Draft {
  email: string;
  password: string;
  full_name: string;
  country: string;
  city: string;
  linkedin: string;
  also_mentor: boolean;
  s_name: string;
  s_website: string;
  s_country: string;
  s_city: string;
  s_sector: string;
  s_stage: string;
  s_pitch: string;
  terms: boolean;
  privacy: boolean;
  conduct: boolean;
  referral: ReferralDraft;
}

const EMPTY: Draft = {
  email: "",
  password: "",
  full_name: "",
  country: "",
  city: "",
  linkedin: "",
  also_mentor: false,
  s_name: "",
  s_website: "",
  s_country: "",
  s_city: "",
  s_sector: "",
  s_stage: "",
  s_pitch: "",
  terms: false,
  privacy: false,
  conduct: false,
  referral: EMPTY_REFERRAL,
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
  // Invitation emails link with ?invitation=; ?invite= is kept for links already shared.
  const invitation = params.get("invitation") ?? params.get("invite") ?? "";
  // A referral link keeps its code for the visit, so moving between pages does not lose it.
  const refCode = (params.get("ref") ?? storedRefCode()).trim().toUpperCase().slice(0, 12);
  const [refNote, setRefNote] = useState("");
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [step, setStep] = useState(0);
  const [done, setDone] = useState<"pending" | "approved" | null>(null);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [inviteRole, setInviteRole] = useState("");

  const countries = useCountries();
  const sectors = useSectors();
  const stages = useStages();

  // A member arriving from an invitation already has their address chosen for them.
  useEffect(() => {
    if (!invitation) return;
    void unwrap(
      api.POST("/api/v1/auth/invitations/inspect", { body: { token: invitation } }),
    )
      .then((preview) => {
        setDraft((d) => ({ ...d, email: preview.email }));
        setInviteRole(preview.role);
      })
      .catch(() => undefined);
  }, [invitation]);

  // Someone who opened a member's link starts with that member chosen, and can change it.
  useEffect(() => {
    if (!refCode) return;
    rememberRefCode(refCode);
    void unwrap(api.GET("/api/v1/members/referrer-by-code", { params: { query: { code: refCode } } }))
      .then((who) => {
        if (!who.found) return;
        setDraft((d) => ({
          ...d,
          referral: {
            ...d.referral,
            kind: d.referral.kind || "member",
            code: refCode,
            referrer: d.referral.referrer ?? (who.id ? { id: who.id, name: who.name, startup: who.startup, photo: who.photo } : null),
          },
        }));
        setRefNote(who.id ? `You are joining through ${who.name}'s link. You can change this.` : "You are joining through a member's link.");
      })
      .catch(() => undefined);
  }, [refCode]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = useSubmit(async () => {
    const body: components["schemas"]["RegisterRequest"] = {
        email: draft.email.trim(),
        password: draft.password,
        accepted_terms: draft.terms,
        accepted_privacy: draft.privacy,
        accepted_conduct: draft.conduct,
        marketing_consent: true, // members get the newsletter; they can leave it any time
        also_mentor: draft.also_mentor,
        invitation_token: invitation,
        referral: referralBody(draft.referral),
        profile: {
          full_name: draft.full_name.trim(),
          country: draft.country,
          city: draft.city.trim(),
          linkedin_url: draft.linkedin.trim(),
        },
        startup: {
          name: draft.s_name.trim(),
          country: draft.s_country || draft.country,
          city: draft.s_city.trim() || draft.city.trim(),
          sector: draft.s_sector,
          stage: draft.s_stage,
          pitch: draft.s_pitch.trim(),
          website_url: draft.s_website.trim(),
        },
    };
    const { response, error } = await api.POST("/api/v1/auth/register", { body });
    if (!response.ok) {
      await unwrap(Promise.resolve({ error, response }));
      return;
    }
    setDone(response.status === 201 ? "approved" : "pending");
  });

  // Staff invited to the admin console only choose a name and a password: the link already proved
  // the address, so they are signed in and taken straight to the console.
  const staffInvite = Boolean(invitation) && isAdmin([inviteRole]);
  if (status === "authenticated") return <Navigate to={staffInvite ? "/admin" : "/app"} replace />;
  if (staffInvite) return <StaffJoin email={draft.email} invitation={invitation} />;

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
      if (!/linkedin\.com\/./i.test(draft.linkedin.trim()))
        out["profile.linkedin_url"] = "Add the link to your LinkedIn profile, like linkedin.com/in/your-name.";
    } else if (index === 2) {
      if (!draft.s_name.trim()) out["startup.name"] = "Enter the company name.";
      if (!/^(https?:\/\/)?[^\s/]+\.[^\s]{2,}/i.test(draft.s_website.trim()))
        out["startup.website_url"] = "Add your company website, like yourcompany.com.";
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
          <Input
            label="LinkedIn profile"
            type="url"
            inputMode="url"
            autoComplete="url"
            placeholder="linkedin.com/in/your-name"
            hint="Required. Our team uses it to review your application."
            value={draft.linkedin}
            onChange={(e) => set("linkedin", e.target.value)}
            error={err("profile.linkedin_url")}
          />
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
            label="Company name"
            autoComplete="organization"
            value={draft.s_name}
            onChange={(e) => set("s_name", e.target.value)}
            error={err("startup.name")}
          />
          <Input
            label="Company website"
            type="url"
            inputMode="url"
            placeholder="yourcompany.com"
            value={draft.s_website}
            onChange={(e) => set("s_website", e.target.value)}
            error={err("startup.website_url")}
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
          <ReferralFields draft={draft.referral} onChange={(referral) => set("referral", referral)} note={refNote} />
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
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            As a member you will also get the WO Community newsletter. You can unsubscribe from any
            issue, or in your settings, at any time.
          </p>
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

function StaffJoin({ email, invitation }: { email: string; invitation: string }) {
  useDocumentTitle("Join the admin team");
  const { login } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [agree, setAgree] = useState(false);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const submit = useSubmit(async () => {
    const found: Record<string, string> = {};
    if (name.trim().length < 2) found.full_name = "Enter your full name.";
    if (password.length < 10) found.password = "Use at least 10 characters.";
    if (!agree) found.agree = "Accept the terms, privacy policy and code of conduct to continue.";
    setProblems(found);
    if (Object.keys(found).length) return;
    const body = {
      email,
      password,
      accepted_terms: true,
      accepted_privacy: true,
      accepted_conduct: true,
      invitation_token: invitation,
      profile: { full_name: name.trim(), country: "", city: "" },
    } as unknown as components["schemas"]["RegisterRequest"];
    const { response, error } = await api.POST("/api/v1/auth/register", { body });
    if (response.status !== 201) {
      // 202 means the invitation no longer applies (used, revoked or expired).
      if (response.ok) throw new FriendlyError("This invitation has already been used or has expired. Ask an admin to send a new one.");
      await unwrap(Promise.resolve({ error, response }));
      return;
    }
    const outcome = await login(email, password);
    navigate(outcome.kind === "mfa" ? "/login" : "/admin", { replace: true });
  });
  const here = errorsFrom(submit.error).fields;
  return (
    <form className="app-stack app-stack--lg" noValidate onSubmit={(e) => { e.preventDefault(); void submit.run(); }}>
      <div>
        <span className="wo-eyebrow">Admin invitation</span>
        <h1 className="h1" style={{ margin: "var(--space-2) 0" }}>Join the admin team</h1>
        <p className="body app-muted" style={{ margin: 0 }}>Your email is confirmed by this link. Choose a password and you are in.</p>
      </div>
      <FormError error={submit.error} />
      <Input label="Email" type="email" value={email} readOnly />
      <Input label="Full name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} error={here["profile.full_name"] ?? problems.full_name} />
      <Input label="Password" type="password" autoComplete="new-password" hint="At least 10 characters. A passphrase of a few words works well." value={password} onChange={(e) => setPassword(e.target.value)} error={here.password ?? problems.password} />
      <Checkbox
        label={<span>I accept the <Link className="app-link" to="/legal/terms" target="_blank">terms</Link>, <Link className="app-link" to="/legal/privacy" target="_blank">privacy policy</Link> and <Link className="app-link" to="/legal/conduct" target="_blank">code of conduct</Link></span>}
        checked={agree}
        onChange={(e) => setAgree(e.target.checked)}
      />
      {problems.agree ? <span className="wo-error">! {problems.agree}</span> : null}
      <Button size="lg" type="submit" loading={submit.busy} disabled={!email}>Create account and continue</Button>
    </form>
  );
}
