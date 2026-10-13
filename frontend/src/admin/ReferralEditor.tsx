import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Select } from "../components";
import { useDebounced } from "../lib/useDebounced";
import { REFERRAL_SOURCES } from "../referrals/ref";
import { Drawer } from "../ui/Drawer";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";

type Referral = components["schemas"]["ApplicantReferral"];

/** Says in a sentence how someone heard of us, for the drawer and the table. */
export function describeReferral(r: Pick<Referral, "kind" | "kind_label" | "detail" | "referrer"> | undefined): string {
  if (!r || !r.kind) return "Did not say";
  if (r.referrer) return `${r.kind_label}: ${r.referrer.name}`;
  if (r.detail) return `${r.kind_label}: ${r.detail}`;
  return r.kind_label;
}

/** Lets an admin correct how a person says they heard of us, and who brought them. */
export function ReferralEditor({ memberId, current, onClose }: { memberId: string; current: Referral; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(true);
  const [kind, setKind] = useState(current.kind);
  const [detail, setDetail] = useState(current.detail);
  const [referrer, setReferrer] = useState<{ id: string; name: string } | null>(current.referrer ?? null);
  const [term, setTerm] = useState("");
  const query = useDebounced(term.trim());
  const found = useQuery({
    queryKey: ["admin", "referrer-lookup", query],
    enabled: kind === "member" && referrer === null && query.length >= 2,
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { q: query, status: "active", limit: 5 } as never } })),
  });
  const dirty = kind !== current.kind || detail !== current.detail || referrer?.id !== current.referrer?.id;

  const save = useSubmit(async () => {
    await unwrap(
      api.PATCH("/api/v1/admin/members/{user_id}/referral", {
        params: { path: { user_id: memberId } },
        body: { kind: kind as never, detail, referred_by: kind === "member" ? (referrer?.id ?? null) : null },
      }),
    );
    await client.invalidateQueries({ queryKey: ["admin"] });
    toast.show("Referral updated");
    setOpen(false);
    onClose();
  });
  const { fields } = errorsFrom(save.error);

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) onClose();
      }}
      eyebrow="Referral"
      title="How they heard of us"
      subtitle="Correct what they said, or name the member who brought them."
      dirty={dirty}
      footer={
        <>
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button loading={save.busy} onClick={() => void save.run()}>
            Save
          </Button>
        </>
      }
    >
      <div className="wo-form">
        <Select
          label="Source"
          value={kind}
          options={[{ value: "", label: "Did not say" }, ...REFERRAL_SOURCES.map((s) => ({ value: s.value, label: s.label }))]}
          onChange={(e) => {
            setKind(e.target.value);
            if (e.target.value !== "member") setReferrer(null);
          }}
          error={fields.kind}
        />
        {kind === "member" ? (
          referrer ? (
            <div className="wo-referrer">
              <span className="wo-referrer__text">
                <strong>{referrer.name}</strong>
                <span>The member who brought them</span>
              </span>
              <Button variant="ghost" size="sm" onClick={() => setReferrer(null)}>
                Change
              </Button>
            </div>
          ) : (
            <div className="wo-referrer-search">
              <Input label="Find the member" type="search" autoComplete="off" placeholder="Name or email" value={term} onChange={(e) => setTerm(e.target.value)} error={fields.referred_by} />
              {(found.data?.results ?? []).length > 0 ? (
                <ul className="wo-referrer-results" aria-label="Members found">
                  {found.data?.results.map((m) => (
                    <li key={m.id}>
                      <button type="button" className="wo-referrer-results__item" onClick={() => setReferrer({ id: m.id, name: m.name || m.email })}>
                        <span className="wo-referrer__text">
                          <strong>{m.name || m.email}</strong>
                          <span>{m.email}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )
        ) : null}
        {kind !== "search" && kind !== "newsletter" && kind !== "" ? (
          <Input label={kind === "member" ? "Their name, if they are not a member we can find" : "Detail"} maxLength={200} value={detail} onChange={(e) => setDetail(e.target.value)} error={fields.detail} />
        ) : null}
        <FormError error={save.error} listFields />
      </div>
    </Drawer>
  );
}
