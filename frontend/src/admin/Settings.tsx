import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Rows3, Rows4 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Alert, Avatar, Button, Input, Switch } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { mfaAgeSeconds } from "./claims";
import { DataTable } from "./kit/DataTable";
import { StatusChip, type Density } from "./kit/TableBits";
import { ROLE_LABELS, permissionsFor } from "./permissions";
import { usePref } from "./shell/prefs";
import Security from "./Security";
import type { ColumnDef } from "@tanstack/react-table";
import type { components } from "../api/schema";

type Member = components["schemas"]["MemberRow"];

interface Section {
  id: string;
  label: string;
  blurb: string;
  needs?: string;
}

const SECTIONS: Section[] = [
  { id: "profile", label: "Profile", blurb: "Who you are signed in as." },
  { id: "community", label: "Community", blurb: "How the job board and the toolkit behave for everyone.", needs: "settings.manage" },
  { id: "security", label: "Security", blurb: "Two step sign in and recovery codes." },
  { id: "team", label: "Roles and team", blurb: "Everyone who can use this console.", needs: "members.view" },
  { id: "appearance", label: "Appearance", blurb: "How dense tables are." },
];

/** A bar that appears only when a form has unsaved changes. */
function SaveBar({ busy, onSave, onDiscard }: { busy: boolean; onSave: () => void; onDiscard: () => void }) {
  return (
    <div className="adm-savebar" role="region" aria-label="Unsaved changes">
      <p>You have changes that are not saved yet.</p>
      <div className="adm-toolbar">
        <Button variant="ghost" onClick={onDiscard}>Discard</Button>
        <Button loading={busy} onClick={onSave}>Save changes</Button>
      </div>
    </div>
  );
}

function ProfileSection() {
  const { me } = useAuth();
  const roles = me?.roles ?? [];
  const age = mfaAgeSeconds();
  return (
    <section className="adm-card" aria-labelledby="profile-title">
      <h2 className="adm-card__title" id="profile-title">Your account</h2>
      <div className="adm-who" style={{ margin: "var(--space-4) 0" }}>
        <Avatar name={me?.email ?? "Admin"} id={me?.id} size="md" />
        <span className="adm-who__text">
          <span className="adm-who__name">{me?.email}</span>
          <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>{roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ")}</span>
        </span>
      </div>
      <dl className="adm-kv">
        <div className="adm-kv__row"><dt>Status</dt><dd><StatusChip tone={me?.status === "active" ? "success" : "warning"}>{humanise(me?.status ?? "unknown")}</StatusChip></dd></div>
        <div className="adm-kv__row"><dt>Two step sign in</dt><dd>{age === null ? "Not confirmed on this session" : `Confirmed ${age < 60 ? "just now" : `${Math.round(age / 60)} minutes ago`}`}</dd></div>
        <div className="adm-kv__row"><dt>Account id</dt><dd><span className="adm-who__id">{me?.id}</span></dd></div>
      </dl>
      <p className="body-sm app-muted" style={{ margin: "var(--space-4) 0 0" }}>Your name, photo and member details are edited on your <Link to="/app/me">member profile</Link>.</p>
    </section>
  );
}

function CommunitySection({ permissions }: { permissions: Set<string> }) {
  const client = useQueryClient();
  const toast = useToast();
  const jobs = useQuery({ queryKey: ["admin", "job-settings"], queryFn: () => unwrap(api.GET("/api/v1/admin/jobs/settings")) });
  const toolkit = useQuery({
    queryKey: ["admin", "toolkit-settings"],
    enabled: permissions.has("toolkit.settings"),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/settings")),
  });
  const [approval, setApproval] = useState(true);
  const [days, setDays] = useState("30");
  useEffect(() => {
    if (jobs.data) {
      setApproval(jobs.data.require_approval);
      setDays(String(jobs.data.default_duration_days));
    }
  }, [jobs.data]);
  const dirty = jobs.data !== undefined && (approval !== jobs.data.require_approval || Number(days) !== jobs.data.default_duration_days);
  const save = useSubmit(async () => {
    await unwrap(api.PUT("/api/v1/admin/jobs/settings", { body: { require_approval: approval, default_duration_days: Number(days) } }));
    toast.show("Job board settings saved");
    await client.invalidateQueries({ queryKey: ["admin", "job-settings"] });
  });
  return (
    <div className="app-stack app-stack--lg">
      <section className="adm-card" aria-labelledby="jobs-title">
        <h2 className="adm-card__title" id="jobs-title">Job board</h2>
        <p className="adm-card__sub">What happens when a member posts a job.</p>
        <Loaded query={jobs} skeleton={<SkeletonRows count={2} />}>
          {() => (
            <div className="app-stack" style={{ marginTop: "var(--space-5)" }}>
              <FormError error={save.error} />
              <Switch label="New jobs wait for an admin before they go live" checked={approval} onChange={(e) => setApproval(e.target.checked)} />
              <div style={{ maxWidth: 320 }}>
                <Input label="Days a job stays up when it has no deadline" type="number" min={1} max={365} value={days} onChange={(e) => setDays(e.target.value)} />
              </div>
            </div>
          )}
        </Loaded>
      </section>

      {permissions.has("toolkit.settings") ? (
        <section className="adm-card" aria-labelledby="tk-title">
          <h2 className="adm-card__title" id="tk-title">Launch toolkit</h2>
          <p className="adm-card__sub">How the toolkit is set up. These are read only here; they are changed in the back end configuration.</p>
          <Loaded query={toolkit} skeleton={<SkeletonRows count={3} />}>
            {(t) => (
              <dl className="adm-kv" style={{ marginTop: "var(--space-4)" }}>
                <div className="adm-kv__row"><dt>AI provider</dt><dd>{t.ai_provider}{t.ai_fallback_provider ? `, then ${t.ai_fallback_provider}` : ""}</dd></div>
                <div className="adm-kv__row"><dt>AI runs a day</dt><dd>{t.ai_daily_run_ceiling.toLocaleString("en-NG")} at most</dd></div>
                <div className="adm-kv__row"><dt>Ventures per member</dt><dd>{t.max_ventures_per_member}</dd></div>
                <div className="adm-kv__row"><dt>Exports kept for</dt><dd>{t.export_retention_days} days</dd></div>
                {Object.entries(t.features).map(([name, on]) => (
                  <div key={name} className="adm-kv__row"><dt>{humanise(name)}</dt><dd><StatusChip tone={on ? "success" : "neutral"}>{on ? "On" : "Off"}</StatusChip></dd></div>
                ))}
              </dl>
            )}
          </Loaded>
        </section>
      ) : null}

      {dirty ? (
        <SaveBar
          busy={save.busy}
          onSave={() => void save.run()}
          onDiscard={() => {
            setApproval(jobs.data?.require_approval ?? true);
            setDays(String(jobs.data?.default_duration_days ?? 30));
          }}
        />
      ) : null}
    </div>
  );
}

function useRoleMembers(role: string) {
  return useQuery({
    queryKey: ["admin", "team", role],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { role, limit: 100 } } })),
  });
}

function TeamSection() {
  const queries = [useRoleMembers("super_admin"), useRoleMembers("community_admin"), useRoleMembers("content_editor")];
  const loading = queries.some((q) => q.isPending);
  const failed = queries.find((q) => q.isError);
  const stamp = queries.map((q) => q.dataUpdatedAt).join(",");
  const people = useMemo(() => {
    const byId = new Map<string, Member>();
    for (const q of queries) for (const m of q.data?.results ?? []) byId.set(m.id, m);
    return [...byId.values()].sort((x, y) => x.email.localeCompare(y.email));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the stamp changes whenever any list does
  }, [stamp]);
  const columns = useMemo<Array<ColumnDef<Member, unknown>>>(
    () => [
      {
        id: "person",
        header: "Person",
        cell: ({ row }) => (
          <span className="adm-who">
            <Avatar name={row.original.email} id={row.original.id} size="sm" />
            <span className="adm-who__text"><span className="adm-who__name">{row.original.email}</span></span>
          </span>
        ),
      },
      { id: "roles", header: "Roles", cell: ({ row }) => row.original.roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ") },
      { id: "status", header: "Status", cell: ({ row }) => <StatusChip tone={row.original.status === "active" ? "success" : "warning"}>{humanise(row.original.status)}</StatusChip> },
      { id: "last", header: "Last active", cell: ({ row }) => (row.original.last_login ? timeAgo(row.original.last_login) : "Never") },
      { id: "since", header: "Added", cell: ({ row }) => formatDate(row.original.created_at) },
    ],
    [],
  );
  return (
    <section className="adm-card adm-tablecard" aria-labelledby="team-title">
      <div className="adm-tablecard__head">
        <div>
          <h2 className="adm-card__title" id="team-title">Roles and team</h2>
          <p className="adm-card__sub">People with a role in the console. Roles are given by invitation, from the Invitations page.</p>
        </div>
      </div>
      {failed ? (
        <div style={{ padding: "var(--space-6)" }}><ErrorState error={failed.error} onRetry={() => void failed.refetch()} /></div>
      ) : (
        <DataTable
          caption="People with a console role"
          columns={columns}
          data={people}
          getRowId={(m) => m.id}
          loading={loading}
          empty={<div style={{ padding: "var(--space-6)" }}><EmptyState title="Nobody yet">No one has a console role.</EmptyState></div>}
        />
      )}
    </section>
  );
}

function AppearanceSection() {
  const toast = useToast();
  const [density, setDensity] = usePref<Density>("members:density", "comfortable");
  const reset = () => {
    try {
      for (const key of Object.keys(window.localStorage)) if (key.startsWith("wo-admin:")) window.localStorage.removeItem(key);
    } catch {
      // Storage may be blocked, in which case there is nothing saved to clear.
    }
    toast.show("Console preferences cleared. Reload to see the defaults.");
  };
  return (
    <div className="app-stack app-stack--lg">
      <section className="adm-card" aria-labelledby="density-title">
        <h2 className="adm-card__title" id="density-title">Table density</h2>
        <p className="adm-card__sub">How tall the rows in tables are. You can also change it on any table.</p>
        <fieldset className="adm-choices" style={{ marginTop: "var(--space-4)" }}>
          <legend className="wo-visually-hidden">Table density</legend>
          {(["comfortable", "compact"] as const).map((value) => (
            <label key={value} className="adm-choice" data-checked={density === value}>
              <input type="radio" name="density" value={value} checked={density === value} onChange={() => setDensity(value)} />
              {value === "comfortable" ? <Rows3 size={22} strokeWidth={1.5} aria-hidden="true" /> : <Rows4 size={22} strokeWidth={1.5} aria-hidden="true" />}
              <strong>{humanise(value)}</strong>
              <span>{value === "comfortable" ? "56 pixel rows, roomy" : "44 pixel rows, more on screen"}</span>
            </label>
          ))}
        </fieldset>
      </section>
      <section className="adm-card" aria-labelledby="reset-title">
        <h2 className="adm-card__title" id="reset-title">Saved preferences</h2>
        <p className="adm-card__sub">The sidebar state, open menus, columns, density and saved views are kept in this browser only.</p>
        <div style={{ marginTop: "var(--space-4)" }}><Button variant="secondary" onClick={reset}>Clear console preferences</Button></div>
      </section>
    </div>
  );
}

export default function Settings() {
  useDocumentTitle("Settings");
  const { me } = useAuth();
  const [params] = useSearchParams();
  const have = useMemo(() => permissionsFor(me?.roles ?? []), [me?.roles]);
  const sections = SECTIONS.filter((s) => !s.needs || have.has(s.needs));
  const current = sections.find((s) => s.id === params.get("section")) ?? sections[0];
  return (
    <>
      <PageHeader eyebrow="Settings" title="Settings" lead="Your account, community defaults, security and appearance." />
      <div className="adm-settings">
        <nav className="adm-card adm-settings__nav" aria-label="Settings sections">
          <ul>
            {sections.map((s) => (
              <li key={s.id}>
                <Link to={`/admin/settings?section=${s.id}`} className="adm-nav__link" data-current={current?.id === s.id} aria-current={current?.id === s.id ? "page" : undefined}>
                  <span className="adm-nav__label">{s.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="adm-settings__body">
          {current ? <p className="adm-settings__blurb">{current.blurb}</p> : null}
          {current?.id === "profile" ? <ProfileSection /> : null}
          {current?.id === "community" ? <CommunitySection permissions={have} /> : null}
          {current?.id === "security" ? <Security embedded /> : null}
          {current?.id === "team" ? <TeamSection /> : null}
          {current?.id === "appearance" ? <AppearanceSection /> : null}
          {!current ? <Alert tone="info" title="Nothing to show">Your role has no settings to change.</Alert> : null}
        </div>
      </div>
    </>
  );
}
