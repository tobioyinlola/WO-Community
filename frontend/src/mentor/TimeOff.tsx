import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Radio, Select } from "../components";
import { formatDate, formatDateTime } from "../lib/format";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { conflictOf, ConflictDialog, type ConflictSession } from "./Conflicts";
import { QUARTERS } from "./WeeklyEditor";

type Item = components["schemas"]["Exception"];

/** Days off and extra time on one date. These apply as soon as they are added or removed. */
export function TimeOff({ items, zone, onChanged }: { items: Item[]; zone: string; onChanged: () => Promise<void> }) {
  const toast = useToast();
  const client = useQueryClient();
  const [kind, setKind] = useState<"blocked" | "extra">("blocked");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [date, setDate] = useState("");
  const [start, setStart] = useState("14:00");
  const [end, setEnd] = useState("17:00");
  const [pending, setPending] = useState<{ sessions: ConflictSession[]; retry: () => Promise<void> } | null>(null);

  const refresh = async () => {
    await onChanged();
    await client.invalidateQueries({ queryKey: ["slots"] });
  };
  const add = useSubmit(async (acknowledge: boolean = false) => {
    const body = kind === "blocked" ? { type: "blocked" as const, starts_on: from, ends_on: to || from, note: note.trim(), acknowledge } : { type: "extra" as const, date, start, end, note: "", acknowledge };
    try {
      await unwrap(api.POST("/api/v1/me/mentor/exceptions", { body }));
    } catch (error) {
      const sessions = conflictOf(error);
      if (sessions) {
        setPending({ sessions, retry: () => add.run(true).then(() => undefined) });
        return;
      }
      throw error;
    }
    toast.show(kind === "blocked" ? "Days off saved" : "Extra time added");
    setFrom("");
    setTo("");
    setNote("");
    setDate("");
    setPending(null);
    await refresh();
  });
  const remove = async (item: Item, acknowledge = false) => {
    try {
      await unwrap(api.DELETE("/api/v1/me/mentor/exceptions/{item_id}", { params: { path: { item_id: item.id }, query: { acknowledge } } }));
    } catch (error) {
      const sessions = conflictOf(error);
      if (sessions) {
        setPending({ sessions, retry: () => remove(item, true) });
        return;
      }
      toast.show("We could not remove that. Try again.");
      return;
    }
    setPending(null);
    toast.show("Removed");
    await refresh();
  };
  const errors = errorsFrom(add.error).fields;
  const ready = kind === "blocked" ? Boolean(from) : Boolean(date && start && end);

  return (
    <div className="app-stack">
      {items.length === 0 ? (
        <p className="body-sm app-muted" style={{ margin: 0 }}>
          Nothing set. Block a holiday, or add extra time on one date.
        </p>
      ) : (
        <ul className="wo-timeoff" aria-label="Days off and extra time">
          {items.map((item) => (
            <li key={item.id}>
              <span>
                {item.type === "blocked" ? (
                  <>
                    <strong>Off:</strong> {formatDate(item.starts_on)}
                    {item.ends_on && item.ends_on !== item.starts_on ? ` to ${formatDate(item.ends_on)}` : ""}
                    {item.note ? ` (${item.note})` : ""}
                  </>
                ) : (
                  <>
                    <strong>Extra:</strong> {formatDateTime(item.starts_at)} to {formatDateTime(item.ends_at)}
                  </>
                )}
              </span>
              <button type="button" className="wo-iconbtn" aria-label={`Remove ${item.type === "blocked" ? "days off" : "extra time"} from ${formatDate(item.starts_on ?? item.starts_at)}`} onClick={() => void remove(item)}>
                <Trash2 size={16} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <fieldset className="wo-timeoff__add">
        <legend className="wo-label">Add</legend>
        <div className="app-cluster">
          <Radio name="timeoff-kind" label="Days off" checked={kind === "blocked"} onChange={() => setKind("blocked")} />
          <Radio name="timeoff-kind" label="Extra time on one date" checked={kind === "extra"} onChange={() => setKind("extra")} />
        </div>
        <FormError error={add.error} />
        {kind === "blocked" ? (
          <div className="app-formgrid">
            <Input label="First day off" type="date" value={from} onChange={(e) => setFrom(e.target.value)} error={errors.starts_on} />
            <Input label="Last day off (optional)" type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} error={errors.ends_on} />
            <Input label="Note (optional)" value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} />
          </div>
        ) : (
          <div className="app-formgrid">
            <Input label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={errors.date} />
            <Select label="From" options={QUARTERS.map((q) => ({ value: q, label: q }))} value={start} onChange={(e) => setStart(e.target.value)} error={errors.start} />
            <Select label="To" options={QUARTERS.map((q) => ({ value: q, label: q }))} value={end} onChange={(e) => setEnd(e.target.value)} error={errors.end} />
          </div>
        )}
        <p className="caption app-muted" style={{ margin: 0 }}>
          Dates and times are in your zone, {zone.replace(/_/g, " ")}. Sessions already agreed are never removed.
        </p>
        <div>
          <Button variant="secondary" loading={add.busy} disabled={!ready} onClick={() => void add.run(false)}>
            {kind === "blocked" ? "Block these days" : "Add this time"}
          </Button>
        </div>
      </fieldset>
      {pending ? <ConflictDialog sessions={pending.sessions} onKeep={pending.retry} onClose={() => setPending(null)} /> : null}
    </div>
  );
}
