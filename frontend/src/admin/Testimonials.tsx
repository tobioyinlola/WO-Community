import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Button, Checkbox, Input, Modal, Textarea } from "../components";
import { formatDate } from "../lib/format";
import { EmptyState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { StatusChip } from "./kit/TableBits";

type Testimonial = components["schemas"]["AdminTestimonial"];
const KEY = ["admin", "testimonials"];

/** Members' words for the home page, which glide past just above the footer. */
export function Testimonials() {
  useDocumentTitle("Testimonials");
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/admin/testimonials")) });
  const [editing, setEditing] = useState<Testimonial | "new" | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: KEY });

  const toggle = useSubmit(async (row: Testimonial) => {
    await unwrap(api.PATCH("/api/v1/admin/testimonials/{testimonial_id}", { params: { path: { testimonial_id: row.id } }, body: { published: !row.published } }));
    toast.show(row.published ? "Taken off the website" : "Now on the website");
    await refresh();
  });
  const remove = useSubmit(async (row: Testimonial) => {
    if (!window.confirm(`Delete the testimonial from ${row.name}?`)) return;
    await unwrap(api.DELETE("/api/v1/admin/testimonials/{testimonial_id}", { params: { path: { testimonial_id: row.id } } }));
    toast.show("Testimonial deleted");
    await refresh();
  });

  return (
    <>
      <PageHeader
        eyebrow="Content"
        title="Testimonials"
        lead="What members say about the community. Published ones glide past on the home page, just above the footer."
        actions={<Button onClick={() => setEditing("new")}>Add a testimonial</Button>}
      />
      <Alert tone="info" title="Only real words, with permission">
        Add only what a member actually said, and publish it only once they have agreed to it being on the website.
      </Alert>
      <FormError error={toggle.error ?? remove.error} />
      <div style={{ marginTop: "var(--space-6)" }}>
        <Loaded
          query={query}
          skeleton={<SkeletonRows />}
          isEmpty={(rows) => rows.length === 0}
          empty={<EmptyState title="No testimonials yet">When a member tells you what the community did for them, ask if you may share it, then add it here.</EmptyState>}
        >
          {(rows) => (
            <div className="adm-tablewrap">
              <table className="adm-table">
                <caption className="wo-visually-hidden">Testimonials</caption>
                <thead>
                  <tr>
                    <th scope="col">Order</th>
                    <th scope="col">Quote</th>
                    <th scope="col">Who</th>
                    <th scope="col">Status</th>
                    <th scope="col">Added</th>
                    <th scope="col"><span className="wo-visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.position}</td>
                      <td style={{ whiteSpace: "normal", minWidth: "18rem" }}>&ldquo;{row.quote}&rdquo;</td>
                      <td>
                        <strong>{row.name}</strong>
                        {row.role ? <div className="app-faint">{row.role}</div> : null}
                      </td>
                      <td>
                        {row.published ? <StatusChip tone="success">On the website</StatusChip> : row.consent_confirmed ? <StatusChip tone="neutral">Hidden</StatusChip> : <StatusChip tone="warning">Needs permission</StatusChip>}
                      </td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>
                        <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                          <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>Edit</Button>
                          {row.consent_confirmed ? (
                            <Button size="sm" variant="secondary" loading={toggle.busy} onClick={() => void toggle.run(row)}>
                              {row.published ? "Hide" : "Publish"}
                            </Button>
                          ) : null}
                          <Button size="sm" variant="ghost" onClick={() => void remove.run(row)}>Delete</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Loaded>
      </div>
      {editing ? <Editor initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
    </>
  );
}

function Editor({ initial, onClose, onSaved }: { initial: Testimonial | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [quote, setQuote] = useState(initial?.quote ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [role, setRole] = useState(initial?.role ?? "");
  const [position, setPosition] = useState(String(initial?.position ?? 0));
  const [consent, setConsent] = useState(initial?.consent_confirmed ?? false);
  const [published, setPublished] = useState(initial?.published ?? false);

  const save = useSubmit(async () => {
    const body = { quote: quote.trim(), name: name.trim(), role: role.trim(), position: Number(position) || 0, consent_confirmed: consent, published: consent && published };
    if (initial) {
      await unwrap(api.PATCH("/api/v1/admin/testimonials/{testimonial_id}", { params: { path: { testimonial_id: initial.id } }, body }));
    } else {
      await unwrap(api.POST("/api/v1/admin/testimonials", { body }));
    }
    toast.show(body.published ? "Saved, and on the website" : "Saved");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;

  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Testimonials"
      title={initial ? `Edit ${initial.name}'s testimonial` : "Add a testimonial"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={save.busy} onClick={() => void save.run()}>Save</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={save.error} />
        <Textarea label="What they said" rows={4} maxLength={400} value={quote} onChange={(e) => setQuote(e.target.value)} error={errors.quote} hint="Their own words, up to 400 characters. Leave out the quotation marks." />
        <div className="app-grid">
          <Input label="Name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
          <Input label="Role and company (optional)" maxLength={160} value={role} onChange={(e) => setRole(e.target.value)} error={errors.role} hint="For example: Founder, Kuda Foods" />
        </div>
        <Input label="Order on the page" type="number" min={0} max={999} value={position} onChange={(e) => setPosition(e.target.value)} error={errors.position} hint="Lower numbers come first." />
        <Checkbox
          label="They said this and agreed to it being shown on the website"
          checked={consent}
          onChange={(e) => {
            setConsent(e.target.checked);
            if (!e.target.checked) setPublished(false);
          }}
        />
        {errors.consent_confirmed ? <p className="body-sm" style={{ color: "var(--danger-text)", margin: 0 }}>{errors.consent_confirmed}</p> : null}
        <Checkbox label="Show it on the website" checked={published} disabled={!consent} onChange={(e) => setPublished(e.target.checked)} />
      </div>
    </Modal>
  );
}
