import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthProvider";
import { Avatar, Badge, Button, Input, Modal, Select, Switch, Textarea } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, Skeleton } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { DataTable } from "./kit/DataTable";
import { StatusChip } from "./kit/TableBits";
import { ROLE_LABELS } from "./permissions";
import { useStepUp } from "./StepUp";

type Member = components["schemas"]["MemberRow"];
type Role = components["schemas"]["Role"];
type Invitation = components["schemas"]["Invitation"];
type TeamRole = components["schemas"]["TeamRoleEnum"];

const TEAM_ROLES: TeamRole[] = ["content_editor", "community_admin", "super_admin"];

function useRoleMembers(role: string) {
  return useQuery({
    queryKey: ["admin", "team", "members", role],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { role, limit: 100 } } })),
  });
}

function InviteDialog({ roles, onClose }: { roles: Role[]; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TeamRole>("community_admin");
  const [message, setMessage] = useState("");
  const chosen = roles.find((r) => r.role === role);
  const submit = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/invitations", { body: { email: email.trim(), role, message: message.trim() } })));
    toast.show(`Invitation sent to ${email.trim()}`);
    await client.invalidateQueries({ queryKey: ["admin", "team"] });
    await client.invalidateQueries({ queryKey: ["admin", "invitations"] });
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Team"
      title="Invite a teammate"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={!email.trim()} onClick={() => void submit.run()}>Send invitation</Button>
        </>
      }
    >
      <form className="app-stack" noValidate onSubmit={(e) => { e.preventDefault(); void submit.run(); }}>
        <FormError error={submit.error} />
        <Input label="Email address" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Select label="Role" options={TEAM_ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] ?? humanise(r) }))} value={role} onChange={(e) => setRole(e.target.value as TeamRole)} />
        {chosen ? (
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            {chosen.blurb} {chosen.role === "super_admin" ? "A super admin can also invite and remove other teammates, so give this role sparingly." : ""}
          </p>
        ) : null}
        <Textarea label="A personal note (optional)" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
        <p className="body-sm app-muted" style={{ margin: 0 }}>
          They register from the emailed link, are approved straight away, and set up two step sign in the first time they open the console.
        </p>
      </form>
    </Modal>
  );
}

function RolesDialog({ person, current, onClose }: { person: Member; current: string[]; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pendingRevoke, setPendingRevoke] = useState<TeamRole | null>(null);
  const change = async (role: TeamRole, action: "grant" | "revoke") => {
    setBusy(role);
    setError(null);
    try {
      await guard(() => unwrap(api.POST("/api/v1/admin/members/{user_id}/role", { params: { path: { user_id: person.id } }, body: { role, action, reason: "" } })));
      toast.show(action === "grant" ? `${ROLE_LABELS[role]} role given` : `${ROLE_LABELS[role]} role taken away`);
      await client.invalidateQueries({ queryKey: ["admin", "team"] });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Modal open onClose={onClose} eyebrow="Team" title={`Roles for ${person.email}`} actions={<Button onClick={onClose}>Done</Button>}>
        <div className="app-stack">
          <FormError error={error} />
          <p className="body-sm app-muted adm-wrap" style={{ margin: 0 }}>
            Changes apply at once and sign {person.email} out everywhere, so their next page load uses the new access.
          </p>
          {TEAM_ROLES.map((role) => {
            const on = current.includes(role);
            return (
              <Switch
                key={role}
                label={ROLE_LABELS[role] ?? humanise(role)}
                checked={on}
                disabled={busy !== null}
                onChange={() => (on ? setPendingRevoke(role) : void change(role, "grant"))}
              />
            );
          })}
        </div>
      </Modal>
      {pendingRevoke ? (
        <ConfirmDialog
          title={`Take away the ${ROLE_LABELS[pendingRevoke]?.toLowerCase()} role?`}
          body={`${person.email} loses what that role allows straight away.`}
          confirmLabel="Take it away"
          tone="danger"
          onConfirm={() => change(pendingRevoke, "revoke")}
          onClose={() => setPendingRevoke(null)}
        />
      ) : null}
    </>
  );
}

function Pending({ canManage }: { canManage: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const invites = useQuery({
    queryKey: ["admin", "team", "invitations"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/invitations", { params: { query: { role: "team", limit: 50 } } })),
  });
  const open = (invites.data?.results ?? []).filter((i) => ["sent", "opened", "expired"].includes(i.status));
  if (open.length === 0) return null;
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "team"] });
  const resend = async (i: Invitation) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/invitations/{invitation_id}/resend", { params: { path: { invitation_id: i.id } } })));
    toast.show("Invitation sent again");
    await refresh();
  };
  const withdraw = async (i: Invitation) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/invitations/{invitation_id}/revoke", { params: { path: { invitation_id: i.id } } })));
    toast.show("Invitation withdrawn");
    await refresh();
  };
  return (
    <section className="adm-card" aria-labelledby="pending-title">
      <h2 className="adm-card__title" id="pending-title">Waiting to join</h2>
      <p className="adm-card__sub">Invited, but they have not registered yet.</p>
      <ul className="app-stack" style={{ listStyle: "none", margin: "var(--space-4) 0 0", padding: 0 }}>
        {open.map((i) => (
          <li key={i.id} className="app-cluster" style={{ justifyContent: "space-between" }}>
            <span style={{ minWidth: 0 }}>
              <span className="adm-who__name adm-wrap">{i.email}</span>{" "}
              <Badge variant="neutral">{ROLE_LABELS[i.role] ?? humanise(i.role)}</Badge>{" "}
              <span className="caption app-muted">{i.status === "expired" ? "expired" : `sent ${timeAgo(i.last_sent_at || i.created_at)}`}</span>
            </span>
            {canManage ? (
              <span className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <Button size="sm" variant="secondary" onClick={() => void resend(i)}>Resend</Button>
                {i.status !== "expired" ? <Button size="sm" variant="ghost" onClick={() => void withdraw(i)}>Withdraw</Button> : null}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Matrix({ roles }: { roles: Role[] | undefined }) {
  return (
    <section className="adm-card" aria-labelledby="matrix-title">
      <h2 className="adm-card__title" id="matrix-title">What each role can do</h2>
      <p className="adm-card__sub">The same list the platform checks on every request. A role includes everything in the one before it.</p>
      <div className="adm-rolegrid" style={{ marginTop: "var(--space-4)" }}>
        {roles === undefined ? <Skeleton height={140} /> : roles.map((r) => (
          <article key={r.role} className="adm-rolecard">
            <h3 className="h4">{r.title} <span className="caption app-muted">· {r.people} {r.people === 1 ? "person" : "people"}</span></h3>
            <p className="body-sm app-muted" style={{ margin: "var(--space-1) 0 0" }}>{r.blurb}</p>
            <details style={{ marginTop: "var(--space-3)" }}>
              <summary>{r.permissions.length} permissions</summary>
              <ul className="adm-perms">{r.permissions.map((p) => <li key={p}>{p}</li>)}</ul>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}

export function TeamSection({ permissions }: { permissions: Set<string> }) {
  const { me } = useAuth();
  const canManage = permissions.has("roles.manage");
  const queries = [useRoleMembers("super_admin"), useRoleMembers("community_admin"), useRoleMembers("content_editor")];
  const roles = useQuery({ queryKey: ["admin", "team", "roles"], queryFn: () => unwrap(api.GET("/api/v1/admin/roles")) });
  const [inviting, setInviting] = useState(false);
  const [managing, setManaging] = useState<string | null>(null);
  const loading = queries.some((q) => q.isPending);
  const failed = queries.find((q) => q.isError);
  const stamp = queries.map((q) => q.dataUpdatedAt).join(",");
  const people = useMemo(() => {
    const byId = new Map<string, Member>();
    for (const q of queries) for (const m of q.data?.results ?? []) byId.set(m.id, m);
    return [...byId.values()].sort((x, y) => x.email.localeCompare(y.email));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the stamp changes whenever any list does
  }, [stamp]);
  const managed = people.find((p) => p.id === managing) ?? null;

  const columns = useMemo<Array<ColumnDef<Member, unknown>>>(
    () => [
      {
        id: "person",
        header: "Person",
        cell: ({ row }) => (
          <span className="adm-who">
            <Avatar name={row.original.email} id={row.original.id} size="sm" />
            <span className="adm-who__text"><span className="adm-who__name adm-wrap">{row.original.email}</span></span>
          </span>
        ),
      },
      { id: "roles", header: "Roles", cell: ({ row }) => row.original.roles.filter((r) => r !== "member").map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ") },
      { id: "status", header: "Status", cell: ({ row }) => <StatusChip tone={row.original.status === "active" ? "success" : "warning"}>{humanise(row.original.status)}</StatusChip> },
      { id: "last", header: "Last active", cell: ({ row }) => (row.original.last_login ? timeAgo(row.original.last_login) : "Never") },
      { id: "since", header: "Added", cell: ({ row }) => formatDate(row.original.created_at) },
      ...(canManage
        ? [
            {
              id: "actions",
              header: () => <span className="wo-visually-hidden">Actions</span>,
              cell: ({ row }: { row: { original: Member } }) =>
                row.original.id === me?.id ? (
                  <span className="caption app-muted">You</span>
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setManaging(row.original.id)} aria-label={`Change roles for ${row.original.email}`}>Change roles</Button>
                ),
            } satisfies ColumnDef<Member, unknown>,
          ]
        : []),
    ],
    [canManage, me?.id],
  );

  return (
    <div className="app-stack app-stack--lg">
      <section className="adm-card adm-tablecard" aria-labelledby="team-title">
        <div className="adm-tablecard__head">
          <div>
            <h2 className="adm-card__title" id="team-title">Roles and team</h2>
            <p className="adm-card__sub">
              {canManage ? "Invite people to the console and decide what each of them can do." : "People with a role in the console. Only a super admin can change the team."}
            </p>
          </div>
          {canManage ? <Button onClick={() => setInviting(true)}><UserPlus size={16} strokeWidth={1.5} aria-hidden="true" /> Invite a teammate</Button> : null}
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
      <Pending canManage={canManage} />
      <Matrix roles={roles.data} />
      {inviting && roles.data ? <InviteDialog roles={roles.data} onClose={() => setInviting(false)} /> : null}
      {managed ? <RolesDialog person={managed} current={managed.roles} onClose={() => setManaging(null)} /> : null}
    </div>
  );
}
