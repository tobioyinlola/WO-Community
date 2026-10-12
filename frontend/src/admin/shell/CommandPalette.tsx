import { Command } from "cmdk";
import { ArrowRight, Search, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { flatNav } from "./nav";

interface Action {
  id: string;
  label: string;
  to: string;
  needs: string;
  hint: string;
}

const ACTIONS: Action[] = [
  { id: "approve-next", label: "Approve the next request", to: "/admin/approvals?next=1", needs: "members.approve", hint: "Opens the oldest request waiting" },
  { id: "invite", label: "Invite someone", to: "/admin/invitations", needs: "invitations.manage", hint: "Send an invitation that is approved on arrival" },
  { id: "new-story", label: "Write a story", to: "/admin/news?new=1", needs: "editorial.manage", hint: "Start a news draft" },
  { id: "new-event", label: "Create an event", to: "/admin/events?new=1", needs: "events.manage", hint: "Start an event draft" },
  { id: "new-newsletter", label: "Write a newsletter", to: "/admin/email?new=1", needs: "campaigns.send", hint: "Start an email draft" },
];

/** Cmd or Ctrl K: jump to any page, run a quick action, or search members. */
export function CommandPalette({ open, onOpenChange, permissions }: { open: boolean; onOpenChange: (open: boolean) => void; permissions: Set<string> }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const pages = useMemo(() => flatNav(permissions), [permissions]);
  const actions = ACTIONS.filter((a) => permissions.has(a.needs));
  const go = (to: string) => {
    onOpenChange(false);
    setQuery("");
    navigate(to);
  };
  const term = query.trim();
  // Matching is done here, so a page or an action always comes before searching members.
  const words = term.toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (text: string) => words.every((w) => text.toLowerCase().includes(w));
  const shownActions = actions.filter((a) => matches(`${a.label} ${a.hint}`));
  const shownPages = pages.filter((p) => matches(`${p.group} ${p.label}`));
  const nothing = term && shownActions.length === 0 && shownPages.length === 0 && !permissions.has("members.view");
  return (
    <Command.Dialog open={open} onOpenChange={onOpenChange} shouldFilter={false} label="Search the console" className="adm-palette" overlayClassName="adm-scrim" contentClassName="adm-palette__box">
      <div className="adm-palette__bar">
        <Search size={18} strokeWidth={1.5} aria-hidden="true" />
        <Command.Input value={query} onValueChange={setQuery} placeholder="Jump to a page, run an action or find a member" className="adm-palette__input" />
        <kbd className="adm-kbd" aria-hidden="true">Esc</kbd>
      </div>
      <Command.List className="adm-palette__list">
        {nothing ? <p className="adm-palette__empty">Nothing matches. Try a page name such as “jobs” or “events”.</p> : null}
        {shownActions.length > 0 ? (
          <Command.Group heading="Quick actions">
            {shownActions.map((a) => (
              <Command.Item key={a.id} value={`${a.label} ${a.hint}`} onSelect={() => go(a.to)} className="adm-palette__item">
                <Zap size={18} strokeWidth={1.5} aria-hidden="true" />
                <span>{a.label}</span>
                <span className="adm-palette__hint">{a.hint}</span>
              </Command.Item>
            ))}
          </Command.Group>
        ) : null}
        {shownPages.length > 0 ? (
        <Command.Group heading="Pages">
          {shownPages.map((p) => (
            <Command.Item key={p.id} value={`${p.group} ${p.label}`} onSelect={() => go(p.to)} className="adm-palette__item">
              <ArrowRight size={18} strokeWidth={1.5} aria-hidden="true" />
              <span>{p.label}</span>
              {p.group ? <span className="adm-palette__hint">{p.group}</span> : null}
              {p.soon ? <span className="adm-nav__soon">Soon</span> : null}
            </Command.Item>
          ))}
        </Command.Group>
        ) : null}
        {term && permissions.has("members.view") ? (
          <Command.Group heading="Members">
            <Command.Item value={`find members ${term}`} onSelect={() => go(`/admin/members?q=${encodeURIComponent(term)}`)} className="adm-palette__item">
              <Search size={18} strokeWidth={1.5} aria-hidden="true" />
              <span>Find members matching “{term}”</span>
            </Command.Item>
          </Command.Group>
        ) : null}
      </Command.List>
    </Command.Dialog>
  );
}
