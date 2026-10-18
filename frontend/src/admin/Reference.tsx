import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Modal } from "../components";
import { EmptyState, Loaded, PageHeader, SkeletonRows, TableScroll, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { useStepUp } from "./StepUp";

type Kind = "sectors" | "stages" | "skills" | "course_categories";
type Entry = components["schemas"]["ReferenceItem"];

const KINDS: Array<{ id: Kind; label: string; blurb: string }> = [
  { id: "sectors", label: "Sectors", blurb: "The industries startups and members can pick." },
  { id: "stages", label: "Stages", blurb: "How far along a startup is." },
  { id: "skills", label: "Skills", blurb: "What members can say they are good at." },
  { id: "course_categories", label: "Course categories", blurb: "What courses are about. Admins pick one for each course, and members filter the catalogue by them." },
];

function AddEntry({ kind, onClose, onSaved }: { kind: Kind; onClose: () => void; onSaved: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [name, setName] = useState("");
  const save = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/reference/{kind}", { params: { path: { kind } }, body: { name: name.trim(), slug: "" } })));
    toast.show("Entry added");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Lists" title="Add an entry"
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!name.trim()} onClick={() => void save.run()}>Add</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name ?? errors.slug} />
      </div>
    </Modal>
  );
}

function List({ kind }: { kind: Kind }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Entry | null>(null);
  const [renaming, setRenaming] = useState<{ entry: Entry; name: string } | null>(null);
  const query = useQuery({ queryKey: ["admin", "reference", kind], queryFn: () => unwrap(api.GET("/api/v1/admin/reference/{kind}", { params: { path: { kind } } })) });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "reference", kind] });
  const patch = async (entry: Entry, body: { name?: string; active?: boolean }) => {
    await guard(() => unwrap(api.PATCH("/api/v1/admin/reference/{kind}/{item_id}", { params: { path: { kind, item_id: entry.id } }, body })));
    await refresh();
  };
  const move = async (entries: Entry[], index: number, by: number) => {
    const ids = entries.map((e) => e.id);
    const [moved] = ids.splice(index, 1);
    if (moved) ids.splice(index + by, 0, moved);
    await guard(() => unwrap(api.PUT("/api/v1/admin/reference/{kind}/order", { params: { path: { kind } }, body: { ids } })));
    await refresh();
  };
  const rename = useSubmit(async () => {
    if (!renaming) return;
    await patch(renaming.entry, { name: renaming.name.trim() });
    toast.show("Name changed");
    setRenaming(null);
  });
  return (
    <>
      <div className="app-cluster" style={{ justifyContent: "flex-end", marginBottom: "var(--space-4)" }}><Button onClick={() => setAdding(true)}>Add an entry</Button></div>
      <Loaded query={query} skeleton={<SkeletonRows count={6} />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="Nothing here yet">Add the first entry.</EmptyState>}>
        {(entries) => (
          <TableScroll label={KINDS.find((k) => k.id === kind)?.label ?? "List"}>
            <table className="app-table">
              <caption className="wo-visually-hidden">{kind}</caption>
              <thead><tr><th scope="col">Name</th><th scope="col">Used by</th><th scope="col">Shown</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={e.id}>
                    <th scope="row">{e.name}{!e.active ? <> <Badge variant="neutral">Retired</Badge></> : null}</th>
                    <td>{e.usage}</td>
                    <td>{e.active ? "Yes" : "No"}</td>
                    <td>
                      <div className="app-cluster" style={{ flexWrap: "nowrap", gap: "var(--space-1)" }}>
                        <button type="button" className="app-iconbtn" aria-label={`Move ${e.name} up`} disabled={i === 0} onClick={() => void move(entries, i, -1)}><ArrowUp size={18} strokeWidth={1.5} /></button>
                        <button type="button" className="app-iconbtn" aria-label={`Move ${e.name} down`} disabled={i === entries.length - 1} onClick={() => void move(entries, i, 1)}><ArrowDown size={18} strokeWidth={1.5} /></button>
                        <Button size="sm" variant="ghost" onClick={() => setRenaming({ entry: e, name: e.name })} aria-label={`Rename ${e.name}`}>Rename</Button>
                        <Button size="sm" variant="ghost" onClick={() => void patch(e, { active: !e.active })} aria-label={`${e.active ? "Retire" : "Bring back"} ${e.name}`}>{e.active ? "Retire" : "Bring back"}</Button>
                        {e.usage === 0 ? <Button size="sm" variant="ghost" onClick={() => setRemoving(e)} aria-label={`Delete ${e.name}`}>Delete</Button> : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        )}
      </Loaded>
      {adding ? <AddEntry kind={kind} onClose={() => setAdding(false)} onSaved={refresh} /> : null}
      {renaming ? (
        <Modal open onClose={() => setRenaming(null)} eyebrow="Lists" title="Rename this entry"
          actions={<><Button variant="ghost" onClick={() => setRenaming(null)}>Cancel</Button><Button loading={rename.busy} disabled={!renaming.name.trim()} onClick={() => void rename.run()}>Save</Button></>}>
          <div className="app-stack"><FormError error={rename.error} /><Input label="Name" value={renaming.name} onChange={(e) => setRenaming({ ...renaming, name: e.target.value })} /></div>
        </Modal>
      ) : null}
      {removing ? (
        <ConfirmDialog title="Delete this entry?" body={`“${removing.name}” is deleted. It is not used anywhere, so nothing changes for members.`} confirmLabel="Delete" tone="danger" onClose={() => setRemoving(null)}
          onConfirm={async () => { await guard(() => unwrap(api.DELETE("/api/v1/admin/reference/{kind}/{item_id}", { params: { path: { kind, item_id: removing.id } } }))); toast.show("Entry deleted"); await refresh(); }} />
      ) : null}
    </>
  );
}

export default function Reference() {
  useDocumentTitle("Lists");
  const [params, setParams] = useSearchParams();
  const asked = params.get("list");
  const [kind, setKindState] = useState<Kind>(KINDS.some((k) => k.id === asked) ? (asked as Kind) : "sectors");
  const setKind = (next: Kind) => {
    setKindState(next);
    setParams(next === "sectors" ? {} : { list: next }, { replace: true });
  };
  const current = KINDS.find((k) => k.id === kind);
  return (
    <>
      <PageHeader eyebrow="Settings" title="Lists" lead="The choices members see in forms and filters. Retire an entry to hide it without losing the records that use it." />
      <div role="tablist" aria-label="Lists" className="app-cluster" style={{ marginBottom: "var(--space-4)" }}>
        {KINDS.map((k) => (
          <button key={k.id} type="button" role="tab" id={`ref-${k.id}`} aria-selected={kind === k.id} aria-controls={`ref-panel-${k.id}`} className="app-react" onClick={() => setKind(k.id)}>{k.label}</button>
        ))}
      </div>
      <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>{current?.blurb}</p>
      <Card>
        <div role="tabpanel" id={`ref-panel-${kind}`} aria-labelledby={`ref-${kind}`}><List kind={kind} /></div>
      </Card>
    </>
  );
}
