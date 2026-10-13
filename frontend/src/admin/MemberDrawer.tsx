import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useCountries } from "../api/reference";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthProvider";
import { Avatar, Button, Input, Modal, Select, Textarea } from "../components";
import { formatDate, formatDateTime, humanise, timeAgo } from "../lib/format";
import { ErrorState, Skeleton } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { StatusChip, type Tone } from "./kit/TableBits";
import { permissionsFor, ROLE_LABELS } from "./permissions";
import { useStepUp } from "./StepUp";

type Full = components["schemas"]["MemberFull"];

const TONE: Record<string, Tone> = { active: "success", pending: "warning", suspended: "danger", removed: "neutral", rejected: "neutral" };
const CONSOLE_ROLES = ["content_editor", "community_admin", "super_admin"];

export type DrawerAction = "approve" | "reject" | "suspend" | "reinstate";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`md-${id}`}>
      <h3 className="adm-sheet__h" id={`md-${id}`}>{title}</h3>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="adm-kv">
      {rows.map(([k, v]) => (
        <div key={k} className="adm-kv__row"><dt>{k}</dt><dd>{v === "" || v == null ? <span className="app-faint">Not given</span> : v}</dd></div>
      ))}
    </dl>
  );
}

function RoleDialog({ member, onClose, onDone }: { member: Full; onClose: () => void; onDone: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [role, setRole] = useState(CONSOLE_ROLES[0] ?? "");
  const has = member.roles.includes(role);
  const submit = useSubmit(async () => {
    await guard(() =>
      unwrap(api.POST("/api/v1/admin/members/{user_id}/role", { params: { path: { user_id: member.id } }, body: { role: role as "content_editor", action: has ? "revoke" : "grant", reason: "" } })),
    );
    toast.show(has ? "Role removed" : "Role given");
    await onDone();
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title="Change console role"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} onClick={() => void submit.run()}>{has ? "Remove role" : "Give role"}</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} listFields />
        <p className="body" style={{ margin: 0 }}>Console roles let a person sign in to the admin console. Only an active account can have one, and their sessions end so the change applies at once.</p>
        <Select label="Role" value={role} onChange={(e) => setRole(e.target.value)} options={CONSOLE_ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] ?? humanise(r) }))} />
        <p className="body-sm app-muted" style={{ margin: 0 }}>{member.name} {has ? "has this role now." : "does not have this role."}</p>
      </div>
    </Modal>
  );
}

function DeleteDialog({ member, onClose, onDone }: { member: Full; onClose: () => void; onDone: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const ready = typed.trim().toLowerCase() === member.email.toLowerCase() && reason.trim().length > 0;
  const submit = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/members/{user_id}/remove", { params: { path: { user_id: member.id } }, body: { reason: reason.trim() } })));
    toast.show("Member removed");
    await onDone();
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title="Delete this member?"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="danger" loading={submit.busy} disabled={!ready} onClick={() => void submit.run()}>Delete member</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} listFields />
        <p className="body" style={{ margin: 0 }}>Their access ends and their profile is taken down. To confirm, type their email address: <strong>{member.email}</strong></p>
        <Input label="Their email address" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        <Textarea label="Reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} hint="This is kept in the audit log." />
      </div>
    </Modal>
  );
}

/** One member in full, opened from the members list. The address is /admin/members/:id. */
export function MemberDrawer({ memberId, onClose, onAct }: { memberId: string; onClose: () => void; onAct: (kind: DrawerAction, member: { id: string; email: string }) => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const { me } = useAuth();
  const have = useMemo(() => permissionsFor(me?.roles ?? []), [me?.roles]);
  const countries = useCountries();
  const [dialog, setDialog] = useState<"role" | "delete" | null>(null);
  const detail = useQuery({
    queryKey: ["admin", "member", memberId],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members/{user_id}", { params: { path: { user_id: memberId } } })),
  });
  const m = detail.data;
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  const resend = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/admin/members/{user_id}/resend-verification", { params: { path: { user_id: memberId } } }));
    toast.show("Verification email sent");
    await refresh();
  });
  const country = (code: string) => (code ? (countries.data?.find((c) => c.value === code)?.label ?? code) : "");

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="adm-scrim adm-scrim--blur" />
        <Dialog.Content className="adm-sheet" aria-describedby={undefined} onInteractOutside={(e) => { if ((e.target as HTMLElement | null)?.closest?.(".app-toasts")) e.preventDefault(); }}>
          <header className="adm-sheet__head">
            {m ? (
              <div className="adm-who">
                <Avatar name={m.name} id={m.id} size="sm" />
                <span className="adm-who__text">
                  <Dialog.Title className="adm-who__name">{m.name}</Dialog.Title>
                  <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>
                    {m.roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ") || "No role yet"} · <StatusChip tone={TONE[m.status] ?? "neutral"}>{humanise(m.status)}</StatusChip>
                  </span>
                </span>
              </div>
            ) : (
              <Dialog.Title className="adm-sheet__label">Member</Dialog.Title>
            )}
            <Dialog.Close className="adm-iconbtn adm-iconbtn--ring" aria-label="Close"><X size={18} strokeWidth={1.5} aria-hidden="true" /></Dialog.Close>
          </header>

          {m ? (
            <div className="adm-sheet__actions" style={{ padding: "var(--space-3) var(--space-5)", flexWrap: "wrap", justifyContent: "flex-start" }}>
              {m.status === "pending" && have.has("members.approve") ? (
                <>
                  <Button size="sm" onClick={() => onAct("approve", m)}>Approve</Button>
                  <Button size="sm" variant="secondary" onClick={() => onAct("reject", m)}>Reject</Button>
                </>
              ) : null}
              {m.status === "active" && have.has("members.suspend") ? <Button size="sm" variant="secondary" onClick={() => onAct("suspend", m)}>Suspend</Button> : null}
              {m.status === "suspended" && have.has("members.suspend") ? <Button size="sm" variant="secondary" onClick={() => onAct("reinstate", m)}>Reinstate</Button> : null}
              {have.has("roles.manage") && m.status === "active" ? <Button size="sm" variant="secondary" onClick={() => setDialog("role")}>Change role</Button> : null}
              {!m.email_verified_at && have.has("members.approve") ? <Button size="sm" variant="secondary" loading={resend.busy} onClick={() => void resend.run()}>Resend verification email</Button> : null}
              {(m.status === "active" || m.status === "suspended") && have.has("members.remove") ? <Button size="sm" variant="danger" onClick={() => setDialog("delete")}>Delete</Button> : null}
            </div>
          ) : null}

          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="adm-sheet__body" tabIndex={0} role="region" aria-label="Member details">
            {detail.isPending ? (
              <>
                <Skeleton height={20} width="60%" />
                <Skeleton height={120} />
                <Skeleton height={120} />
              </>
            ) : detail.isError || !m ? (
              <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
            ) : (
              <>
                <Section id="profile" title="Profile">
                  <Rows
                    rows={[
                      ["Full name", m.profile.full_name],
                      ["Headline", m.profile.headline],
                      ["Bio", m.profile.bio],
                      ["Location", [m.profile.city, country(m.profile.country)].filter(Boolean).join(", ")],
                      ["Startup", [m.profile.startup_name, m.profile.industry, m.profile.stage].filter(Boolean).join(" · ")],
                      ["What they are building", m.profile.pitch],
                      ["Skills", m.profile.skills.join(", ")],
                      ["Open to", m.profile.open_to.map(humanise).join(", ")],
                      ["Website", m.profile.website_url ? <a key="w" href={m.profile.website_url} target="_blank" rel="noopener noreferrer">{m.profile.website_url}</a> : ""],
                      ["LinkedIn", m.profile.linkedin_url ? <a key="l" href={m.profile.linkedin_url} target="_blank" rel="noopener noreferrer">{m.profile.linkedin_url}</a> : ""],
                      ["X", m.profile.x_url],
                      ["Profile completeness", `${m.profile.completeness}%`],
                    ]}
                  />
                </Section>

                <Section id="account" title="Account">
                  <Rows
                    rows={[
                      ["Email", `${m.email}${m.email_verified_at ? " (confirmed)" : " (not confirmed)"}`],
                      ["Joined", formatDateTime(m.created_at)],
                      ["Last active", m.last_login ? timeAgo(m.last_login) : "Never"],
                      ["Invited by", m.account.invited_by?.name ?? ""],
                      ["Referred by", m.account.referred_by?.name ?? ""],
                      ["Approved", m.approved_at ? `${formatDate(m.approved_at)}${m.account.approved_by ? ` by ${m.account.approved_by.name}` : m.approval_source ? ` (${humanise(m.approval_source)})` : ""}` : ""],
                      ["Status note", m.status_reason],
                    ]}
                  />
                </Section>

                <Section id="activity" title="Activity">
                  <Rows rows={[["Posts", String(m.activity.posts)], ["Comments", String(m.activity.comments)], ["Events attended", String(m.activity.events_attended)], ["Jobs posted", String(m.activity.jobs_posted)]]} />
                </Section>

                <Section id="learning" title="Learning">
                  <Rows rows={[["Courses started", String(m.learning.courses_started)], ["Courses completed", String(m.learning.courses_completed)]]} />
                  {m.learning.certificates.length ? (
                    <ul className="app-stack" style={{ listStyle: "none", margin: "var(--space-2) 0 0", padding: 0 }}>
                      {m.learning.certificates.map((c) => (
                        <li key={c.number} className="body-sm">{c.course_title} · <code>{c.number}</code> · {formatDate(c.issued_at)}{c.revoked ? " · revoked" : ""}</li>
                      ))}
                    </ul>
                  ) : null}
                </Section>

                <Section id="mentorship" title="Mentorship">
                  {m.mentorship ? (
                    <Rows
                      rows={[
                        ["Mentor status", `${humanise(m.mentorship.status)}${m.mentorship.paused ? " (paused)" : ""}`],
                        ["Availability", `${m.mentorship.capacity_per_week} a week, ${m.mentorship.session_minutes} minutes each`],
                        ["Pricing", m.mentorship.default_price_minor ? `${(m.mentorship.default_price_minor / 100).toLocaleString("en-NG")} per session` : "Free"],
                        ["Sessions as mentor", String(m.mentorship.sessions_as_mentor)],
                        ["Sessions as mentee", String(m.mentorship.sessions_as_mentee)],
                      ]}
                    />
                  ) : (
                    <p className="body-sm app-muted" style={{ margin: 0 }}>Not a mentor.</p>
                  )}
                </Section>

                <Section id="support" title="Support">
                  {m.open_tickets.length ? (
                    <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                      {m.open_tickets.map((t) => (
                        <li key={t.id} className="body-sm"><Link to={`/admin/support?ticket=${t.id}`}>#{t.number}</Link> {t.subject} · {humanise(t.status)}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="body-sm app-muted" style={{ margin: 0 }}>No open tickets.</p>
                  )}
                </Section>

                {have.has("audit.read") ? (
                  <Section id="audit" title="Audit">
                    {m.audit.length ? (
                      <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                        {m.audit.map((a) => (
                          <li key={a.id} className="body-sm"><code>{a.action}</code> · {timeAgo(a.created_at)}{a.outcome === "failure" ? " · failed" : ""}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="body-sm app-muted" style={{ margin: 0 }}>Nothing recorded yet.</p>
                    )}
                    <p style={{ margin: "var(--space-2) 0 0" }}><Link to={`/admin/audit?target_type=user&target_id=${m.id}`}>See everything in the audit log</Link></p>
                  </Section>
                ) : null}
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
      {m && dialog === "role" ? <RoleDialog member={m} onClose={() => setDialog(null)} onDone={refresh} /> : null}
      {m && dialog === "delete" ? <DeleteDialog member={m} onClose={() => setDialog(null)} onDone={refresh} /> : null}
    </Dialog.Root>
  );
}
