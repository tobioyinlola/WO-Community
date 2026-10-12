import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Avatar, Button, Input, Select } from "../components";
import { useDebounced } from "../lib/useDebounced";
import "../styles/shared-ui.css";
import { REFERRAL_SOURCES } from "./ref";

export interface Referrer {
  id: string;
  name: string;
  startup: string;
  photo: { [key: string]: unknown } | null;
}

export interface ReferralDraft {
  kind: string;
  detail: string;
  referrer: Referrer | null;
  /** The code from a link, kept even when the person changes who referred them. */
  code: string;
}

export const EMPTY_REFERRAL: ReferralDraft = { kind: "", detail: "", referrer: null, code: "" };

/** What the API wants for `referral`. */
export function referralBody(draft: ReferralDraft) {
  return {
    ...(draft.kind ? { kind: draft.kind as never } : {}),
    ...(draft.detail.trim() ? { detail: draft.detail.trim() } : {}),
    ...(draft.kind === "member" && draft.referrer ? { referred_by: draft.referrer.id } : {}),
    ...(draft.code ? { code: draft.code } : {}),
  };
}

function Picker({ draft, onChange }: { draft: ReferralDraft; onChange: (next: ReferralDraft) => void }) {
  const [term, setTerm] = useState("");
  const query = useDebounced(term.trim());
  const found = useQuery({
    queryKey: ["referrer-search", query],
    enabled: query.length >= 3 && draft.referrer === null,
    queryFn: () => unwrap(api.GET("/api/v1/members/search-referrer", { params: { query: { q: query } } })),
    staleTime: 60_000,
  });
  const results = found.data?.results ?? [];

  if (draft.referrer) {
    return (
      <div className="wo-referrer" role="group" aria-label="The member who referred you">
        <Avatar name={draft.referrer.name} id={draft.referrer.id} src={(draft.referrer.photo as { thumb?: string } | null)?.thumb} size="sm" />
        <span className="wo-referrer__text">
          <strong>{draft.referrer.name}</strong>
          {draft.referrer.startup ? <span>{draft.referrer.startup}</span> : null}
        </span>
        <Button variant="ghost" size="sm" onClick={() => onChange({ ...draft, referrer: null })}>
          Change
        </Button>
      </div>
    );
  }

  return (
    <div className="wo-referrer-search">
      <Input
        label="Search for them"
        type="search"
        autoComplete="off"
        placeholder="Their name, or their email address in full"
        hint="Only members who list their name publicly can be found."
        value={term}
        onChange={(e) => setTerm(e.target.value)}
      />
      {results.length > 0 ? (
        <ul className="wo-referrer-results" aria-label="Members found">
          {results.map((r) => (
            <li key={r.id}>
              <button type="button" className="wo-referrer-results__item" onClick={() => onChange({ ...draft, referrer: { id: r.id, name: r.name, startup: r.startup, photo: r.photo } })}>
                <Avatar name={r.name} id={r.id} src={(r.photo as { thumb?: string } | null)?.thumb} size="sm" />
                <span className="wo-referrer__text">
                  <strong>{r.name}</strong>
                  <span>{r.startup || r.headline}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {query.length >= 3 && found.isSuccess && results.length === 0 ? (
        <p className="wo-referrer__none" role="status">
          No member found. You can type their name below instead.
        </p>
      ) : null}
      <Input
        label="Or enter their name"
        autoComplete="off"
        maxLength={200}
        hint="If you cannot find them above."
        value={draft.detail}
        onChange={(e) => onChange({ ...draft, detail: e.target.value })}
      />
    </div>
  );
}

/** "Who referred you?": optional, and kind about it. A member can be searched for or named. */
export function ReferralFields({ draft, onChange, note }: { draft: ReferralDraft; onChange: (next: ReferralDraft) => void; note?: string }) {
  const chosen = REFERRAL_SOURCES.find((s) => s.value === draft.kind);
  return (
    <fieldset className="wo-referral">
      <legend className="wo-referral__legend">Who referred you?</legend>
      <p className="wo-referral__lead">Optional, but it helps us thank the people who bring others in.</p>
      {note ? <p className="wo-referral__note" role="status">{note}</p> : null}
      <Select
        label="How did you hear about us?"
        value={draft.kind}
        onChange={(e) => onChange({ ...draft, kind: e.target.value, detail: "", referrer: e.target.value === "member" ? draft.referrer : null })}
        options={[{ value: "", label: "I would rather not say" }, ...REFERRAL_SOURCES.map((s) => ({ value: s.value, label: s.label }))]}
      />
      {draft.kind === "member" ? <Picker draft={draft} onChange={onChange} /> : null}
      {chosen?.detail && draft.kind !== "member" ? (
        <Input label={chosen.detail} maxLength={200} value={draft.detail} onChange={(e) => onChange({ ...draft, detail: e.target.value })} />
      ) : null}
    </fieldset>
  );
}
