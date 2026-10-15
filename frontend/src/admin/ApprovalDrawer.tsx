import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, ExternalLink, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useCountries } from "../api/reference";
import type { components } from "../api/schema";
import { useEffect, useRef, useState } from "react";
import { Avatar, Button, Input, Textarea } from "../components";
import { messageOf } from "../api/errors";
import { formatDateTime, humanise, timeAgo } from "../lib/format";
import { Skeleton } from "../ui/blocks";
import { MeterBar, StatusChip, type Tone } from "./kit/TableBits";
import { ROLE_LABELS } from "./permissions";
import { describeReferral, ReferralEditor } from "./ReferralEditor";

type Row = components["schemas"]["MemberRow"];

const TONE: Record<string, Tone> = { active: "success", pending: "warning", suspended: "danger", removed: "neutral", rejected: "neutral" };
const STEP: Record<string, string> = {
  registered: "Asked to join",
  email_verified: "Confirmed their email",
  decided: "Decision made",
  last_signed_in: "Last signed in",
};

interface Props {
  member: Row;
  /** Where this request sits in the list on show, for the "2 of 19" line. */
  position: { index: number; total: number };
  onClose: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onApprove: () => void;
  /** True while the reason is being typed. The page sets it so the R key can start it. */
  rejecting: boolean;
  onRejectingChange: (on: boolean) => void;
  onReject: (reason: string) => void;
}

/** The LinkedIn profile, which every application needs before it can be approved. */
function LinkedInField({ userId, url, canAdd }: { userId: string; url: string; canAdd: boolean }) {
  const client = useQueryClient();
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  if (url) {
    return (
      <a href={url} rel="noopener noreferrer" target="_blank">
        {url.replace(/^https:\/\/(www\.)?/, "")}
      </a>
    );
  }
  if (!canAdd) return <>Not given</>;
  const save = async () => {
    setSaving(true);
    setProblem("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/admin/members/{user_id}/linkedin", {
          params: { path: { user_id: userId } },
          body: { linkedin_url: value.trim() },
        }),
      );
      client.setQueryData(["admin", "application", userId], updated);
    } catch (error) {
      setProblem(messageOf(error));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form
      className="app-stack"
      style={{ gap: "var(--space-2)" }}
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) void save();
      }}
    >
      <span className="adm-tile__sub" style={{ color: "var(--danger-text)" }}>
        Missing. Needed before approval: ask them for it, or add the profile you found.
      </span>
      <Input
        label="LinkedIn profile"
        placeholder="linkedin.com/in/their-name"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        error={problem || undefined}
      />
      <div>
        <Button size="sm" type="submit" disabled={!value.trim()} loading={saving}>
          Save LinkedIn
        </Button>
      </div>
    </form>
  );
}

/** The request in full: who asked, what they gave, what has happened, and the decision. */
export function ApprovalDrawer({ member, position, onClose, onPrevious, onNext, onApprove, rejecting, onRejectingChange, onReject }: Props) {
  const [reason, setReason] = useState("");
  const [editingReferral, setEditingReferral] = useState(false);
  const reasonBox = useRef<HTMLDivElement>(null);
  // A different request starts with an empty reason.
  useEffect(() => setReason(""), [member.id]);
  useEffect(() => {
    if (rejecting) reasonBox.current?.querySelector("textarea")?.focus();
  }, [rejecting]);
  const countries = useCountries();
  const application = useQuery({
    queryKey: ["admin", "application", member.id],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members/{user_id}/application", { params: { path: { user_id: member.id } } })),
  });
  const a = application.data;
  const country = (code: string | undefined) => (code ? (countries.data?.find((c) => c.value === code)?.label ?? code) : "Not given");
  const name = a?.profile?.full_name || member.name || member.email;
  const waiting = member.status === "pending";
  // Only a loaded application can say the link is missing; until then approval is not blocked.
  const missingLinkedIn = Boolean(a) && !a?.profile?.linkedin_url;
  const site = a?.startup?.website_url || a?.profile?.website_url;
  const rows: Array<[string, React.ReactNode]> = [
    ["LinkedIn", a ? <LinkedInField userId={member.id} url={a.profile?.linkedin_url ?? ""} canAdd={waiting} /> : "Loading"],
    ["Company website", site ? <a href={site} rel="noopener noreferrer" target="_blank">{site}</a> : "Not given"],
    ["Country", country(a?.profile?.country || member.country)],
    ["City", a?.profile?.city || a?.startup?.city || "Not given"],
    ["Email", member.email_verified_at ? `Confirmed ${timeAgo(member.email_verified_at)}` : "Not confirmed yet"],
    ["Joined with", member.roles.length === 0 ? "No role yet" : member.roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ")],
  ];

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="adm-scrim adm-scrim--blur" />
        <Dialog.Content
          className="adm-sheet"
          aria-describedby={undefined}
          // A click on a toast, such as Undo, is not a click away from the drawer.
          onInteractOutside={(event) => {
            if ((event.target as HTMLElement | null)?.closest?.(".app-toasts")) event.preventDefault();
          }}
        >
          <header className="adm-sheet__head">
            <div className="adm-sheet__meta">
              <span className="adm-sheet__label">Request {member.id.slice(-8)}</span>
              <span className="adm-sheet__count" aria-live="polite">{position.index + 1} of {position.total}</span>
            </div>
            <div className="adm-sheet__nav">
              <button type="button" className="adm-iconbtn adm-iconbtn--ring" onClick={onPrevious} disabled={position.index <= 0} aria-label="Previous request" aria-keyshortcuts="K">
                <ChevronUp size={18} strokeWidth={1.5} aria-hidden="true" />
              </button>
              <button type="button" className="adm-iconbtn adm-iconbtn--ring" onClick={onNext} disabled={position.index >= position.total - 1} aria-label="Next request" aria-keyshortcuts="J">
                <ChevronDown size={18} strokeWidth={1.5} aria-hidden="true" />
              </button>
              <Dialog.Close className="adm-iconbtn adm-iconbtn--ring" aria-label="Close">
                <X size={18} strokeWidth={1.5} aria-hidden="true" />
              </Dialog.Close>
            </div>
          </header>

          {/* A box that scrolls must be focusable so keyboard users can scroll it. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="adm-sheet__body" tabIndex={0} role="region" aria-label="Request details">
            <div>
              <Dialog.Title className="adm-sheet__title">{name}</Dialog.Title>
              <p className="adm-sheet__chips">
                <StatusChip tone={TONE[member.status] ?? "neutral"}>{humanise(member.status)}</StatusChip>
                <span className="adm-sheet__age">{waiting ? "Waiting" : humanise(member.status)} · <time dateTime={member.created_at} title={formatDateTime(member.created_at)}>asked {timeAgo(member.created_at)}</time></span>
              </p>
            </div>

            <div className="adm-sheet__tiles">
              <section className="adm-tile" aria-label="Applicant">
                <p className="adm-tile__label">Applicant</p>
                <div className="adm-who">
                  <Avatar name={name} id={member.id} size="sm" />
                  <span className="adm-who__text">
                    <span className="adm-who__name">{a?.profile?.full_name || member.name || "Name not given"}</span>
                    <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>{member.email}</span>
                  </span>
                </div>
                {member.status === "active" ? (
                  <Link className="adm-tile__link" to={`/app/members/${member.id}`}>Open profile <ExternalLink size={14} strokeWidth={1.5} aria-hidden="true" /></Link>
                ) : null}
              </section>
              <section className="adm-tile" aria-label="Startup">
                <p className="adm-tile__label">Company</p>
                {a?.startup ? (
                  <>
                    <p className="adm-tile__title">{a.startup.name}</p>
                    <p className="adm-tile__sub">{[a.startup.sector, a.startup.stage].filter(Boolean).join(" · ")}</p>
                  </>
                ) : application.isPending ? <Skeleton width="70%" height={16} /> : <p className="adm-tile__sub">No startup given</p>}
              </section>
            </div>

            <section aria-labelledby="det-title">
              <h3 className="adm-sheet__h" id="det-title">Details</h3>
              <dl className="adm-kv">
                {rows.map(([k, v]) => (
                  <div key={k} className="adm-kv__row"><dt>{k}</dt><dd>{v}</dd></div>
                ))}
                <div className="adm-kv__row">
                  <dt>Referred by</dt>
                  <dd>
                    {a?.referral ? describeReferral(a.referral) : "Not available"}
                    {a?.referral?.code_used ? <span className="app-faint"> (link {a.referral.code_used})</span> : null}
                    {a?.referral ? <> <button type="button" className="wo-linkbtn" onClick={() => setEditingReferral(true)}>Edit</button></> : null}
                  </dd>
                </div>
                <div className="adm-kv__row"><dt>Profile completeness</dt><dd>{a?.profile ? <MeterBar value={a.profile.completeness} label="Profile completeness" /> : "Not available"}</dd></div>
                <div className="adm-kv__row"><dt>Startup completeness</dt><dd>{a?.startup ? <MeterBar value={a.startup.completeness} label="Startup completeness" /> : "Not available"}</dd></div>
              </dl>
            </section>

            {a?.startup?.pitch ? (
              <section aria-labelledby="pitch-title">
                <h3 className="adm-sheet__h" id="pitch-title">What they are building</h3>
                <blockquote className="adm-quote">{a.startup.pitch}</blockquote>
              </section>
            ) : null}

            <section aria-labelledby="act-title2">
              <h3 className="adm-sheet__h" id="act-title2">Activity</h3>
              {application.isPending ? (
                <Skeleton width="100%" height={60} />
              ) : (
                <ol className="adm-timeline">
                  {(a?.timeline ?? []).map((e) => (
                    <li key={e.kind} className="adm-timeline__item">
                      <span className="adm-timeline__mark" aria-hidden="true" />
                      <div>
                        <p className="adm-timeline__text">{STEP[e.kind] ?? e.kind}{e.note ? `: ${e.note}` : ""}</p>
                        <p className="adm-timeline__time"><time dateTime={e.at} title={formatDateTime(e.at)}>{timeAgo(e.at)}</time></p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>

          <footer className="adm-sheet__foot" data-asking={rejecting && waiting}>
            {waiting && rejecting ? (
              <form
                className="adm-sheet__reason"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reason.trim()) onReject(reason.trim());
                }}
              >
                <div ref={reasonBox}>
                  <Textarea label="Why are you rejecting this request?" rows={3} hint="They are told it was not accepted. This is kept in the audit log. You can undo for a few seconds." value={reason} onChange={(e) => setReason(e.target.value)} />
                </div>
                <div className="adm-sheet__actions">
                  <Button variant="ghost" onClick={() => onRejectingChange(false)}>Cancel</Button>
                  <Button type="submit" disabled={!reason.trim()}>Reject</Button>
                </div>
              </form>
            ) : waiting ? (
              <div className="adm-sheet__actions">
                <Button variant="secondary" onClick={() => onRejectingChange(true)} aria-keyshortcuts="R">Reject</Button>
                <Button
                  onClick={onApprove}
                  aria-keyshortcuts="A"
                  disabled={missingLinkedIn}
                  title={missingLinkedIn ? "Add their LinkedIn profile first" : undefined}
                >
                  Approve
                </Button>
              </div>
            ) : (
              <p className="adm-sheet__done">This request has already been decided.</p>
            )}
          </footer>
            {editingReferral && a?.referral ? <ReferralEditor memberId={member.id} current={a.referral} onClose={() => setEditingReferral(false)} /> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
