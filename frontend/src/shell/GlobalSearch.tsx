/* A combobox keeps focus in the input and points at the active option with aria-activedescendant,
   so the options are deliberately not focusable and the keys are handled on the input. */
/* eslint-disable jsx-a11y/click-events-have-key-events, jsx-a11y/interactive-supports-focus */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, CornerDownLeft, Search, SearchX } from "lucide-react";
import { Fragment, useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { isTyping } from "../admin/shell/prefs";
import "../styles/shared-ui.css";
import {
  ADMIN_ORDER,
  GROUP_LABELS,
  MEMBER_ORDER,
  highlightParts,
  iconOf,
  matchLinks,
  memberTarget,
  tagOf,
  type Hit,
  type QuickLink,
  type Scope,
} from "./searchModel";

type Raw = Record<string, Array<{ type: string; id: string; title: string; subtitle?: string; url?: string }>>;

/** Fetches grouped results for the area the person is in. Shared with the full results page. */
export async function fetchResults(scope: Scope, q: string, limit: number, types = ""): Promise<Raw> {
  const query = { q, limit, ...(types ? { types } : {}) };
  if (scope === "admin") return (await unwrap(api.GET("/api/v1/admin/search", { params: { query } }))) as unknown as Raw;
  return (await unwrap(api.GET("/api/v1/search", { params: { query } }))) as unknown as Raw;
}

/** Turns the API's groups into rows with a place to go. */
export function toGroups(scope: Scope, raw: Raw | undefined): Array<{ id: string; label: string; hits: Hit[] }> {
  const order = scope === "admin" ? ADMIN_ORDER : MEMBER_ORDER;
  return order
    .filter((id) => id !== "pages")
    .map((id) => ({
      id,
      label: GROUP_LABELS[id] ?? id,
      hits: (raw?.[id] ?? []).map((r) => ({
        key: `${id}-${r.id}`,
        group: id,
        type: r.type,
        title: r.title,
        subtitle: r.subtitle ?? "",
        to: scope === "admin" ? (r.url ?? "/admin") : memberTarget(r.type, r.id),
      })),
    }))
    .filter((g) => g.hits.length > 0);
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function Marked({ text, term }: { text: string; term: string }) {
  return (
    <>
      {highlightParts(text, term).map((part, i) => (part.match ? <mark key={i}>{part.text}</mark> : <Fragment key={i}>{part.text}</Fragment>))}
    </>
  );
}

type Row =
  | { kind: "hit"; id: string; hit: Hit }
  | { kind: "recent"; id: string; term: string }
  | { kind: "all"; id: string };

interface Props {
  scope: Scope;
  links: QuickLink[];
  /** Where "See all results" goes; the term is added as `?q=`. */
  resultsPath: string;
  placeholder: string;
}

/**
 * The search field of the top bar. Press `/` (or Ctrl or Cmd K) anywhere to reach it. After two
 * letters it lists matches in groups; arrow keys move, Enter opens, Tab jumps to the next group, Esc
 * closes and gives focus back to where it was.
 */
export function GlobalSearch({ scope, links, resultsPath, placeholder }: Props) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const base = useId();
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const debounced = useDebounced(term.trim(), 200);
  const searching = term.trim().length >= 2;

  const results = useQuery({
    queryKey: ["search", scope, debounced],
    enabled: open && debounced.length >= 2,
    queryFn: () => fetchResults(scope, debounced, 4),
    staleTime: 15_000,
  });
  const recents = useQuery({
    queryKey: ["search", "recents", scope],
    enabled: open && !searching,
    queryFn: () => unwrap(api.GET("/api/v1/search/recents", { params: { query: { scope } } })),
  });
  const remember = useMutation({
    mutationFn: (t: string) => unwrap(api.POST("/api/v1/search/recents", { body: { term: t, scope } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["search", "recents", scope] }),
  });
  const clearRecents = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/search/recents", { params: { query: { scope } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["search", "recents", scope] }),
  });

  const close = useCallback(
    (giveBack: boolean) => {
      setOpen(false);
      setActive(-1);
      if (giveBack) {
        const target = returnTo.current;
        if (target && document.contains(target)) target.focus();
        else input.current?.blur();
      }
    },
    [],
  );

  // `/` and Ctrl or Cmd K reach the field from anywhere that is not itself a place to type.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      const combo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      const slash = event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTyping(event.target);
      if (!combo && !slash) return;
      event.preventDefault();
      if (document.activeElement !== input.current) returnTo.current = document.activeElement as HTMLElement | null;
      input.current?.focus();
      input.current?.select();
      setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const away = (event: PointerEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) close(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open, close]);

  // Going somewhere closes the panel.
  useEffect(() => close(false), [location.pathname, location.search, close]);

  const groups = useMemo(() => toGroups(scope, results.data), [scope, results.data]);
  const pageLinks = useMemo(() => matchLinks(links, searching ? term : "", searching ? 4 : 6), [links, term, searching]);

  const rows: Array<{ id: string; label: string; rows: Row[] }> = useMemo(() => {
    const out: Array<{ id: string; label: string; rows: Row[] }> = [];
    if (!searching) {
      const terms = recents.data?.terms ?? [];
      if (terms.length > 0) out.push({ id: "recent", label: "Recent searches", rows: terms.map((t) => ({ kind: "recent", id: `${base}-r-${t}`, term: t })) });
    } else {
      for (const g of groups) out.push({ id: g.id, label: g.label, rows: g.hits.map((hit) => ({ kind: "hit", id: `${base}-${hit.key}`, hit })) });
    }
    if (pageLinks.length > 0) {
      out.push({
        id: "pages",
        label: searching ? "Pages and actions" : "Suggested pages",
        rows: pageLinks.map((l) => ({
          kind: "hit",
          id: `${base}-p-${l.kind ?? "page"}-${l.label}`,
          hit: { key: `p-${l.kind ?? "page"}-${l.label}`, group: "pages", type: l.kind === "Action" ? "action" : "page", title: l.label, subtitle: "", to: l.to },
        })),
      });
    }
    if (searching) out.push({ id: "all", label: "", rows: [{ kind: "all", id: `${base}-all` }] });
    return out;
  }, [searching, recents.data, groups, pageLinks, base]);

  const flat = useMemo(() => rows.flatMap((g) => g.rows), [rows]);
  useEffect(() => setActive(-1), [debounced, open]);

  const go = (to: string) => {
    if (searching) remember.mutate(term.trim());
    close(false);
    navigate(to);
  };
  const seeAll = () => go(`${resultsPath}?q=${encodeURIComponent(term.trim())}`);

  const activate = (row: Row) => {
    if (row.kind === "recent") {
      setTerm(row.term);
      input.current?.focus();
    } else if (row.kind === "all") seeAll();
    else go(row.hit.to);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (flat.length === 0) return;
      setActive((a) => (event.key === "ArrowDown" ? (a + 1) % flat.length : (a <= 0 ? flat.length : a) - 1));
    } else if (event.key === "Tab" && open && flat.length > 0) {
      // Tab moves between groups, so a long list is quick to cross. Past the last group it leaves.
      const firsts: number[] = [];
      let at = 0;
      for (const g of rows) {
        firsts.push(at);
        at += g.rows.length;
      }
      const current = active < 0 ? -1 : firsts.filter((f) => f <= active).length - 1;
      const next = event.shiftKey ? current - 1 : current + 1;
      if (next >= 0 && next < firsts.length) {
        event.preventDefault();
        setActive(firsts[next] ?? 0);
      } else close(false);
    } else if (event.key === "Enter") {
      const row = flat[active];
      if (row) {
        event.preventDefault();
        activate(row);
      }
    }
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (flat[active]) return;
    if (searching) seeAll();
  };

  const listId = `${base}-list`;
  const loading = searching && (results.isFetching || debounced !== term.trim()) && !results.data;
  const empty = searching && !loading && groups.length === 0;
  const activeId = active >= 0 ? flat[active]?.id : undefined;

  return (
    <div className="wo-search" ref={box}>
      <form className="adm-search adm-search--field" role="search" onSubmit={submit}>
        <label className="wo-visually-hidden" htmlFor={`${base}-input`}>
          Search
        </label>
        <Search size={18} strokeWidth={1.5} aria-hidden="true" />
        <input
          id={`${base}-input`}
          ref={input}
          type="search"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-keyshortcuts="/ Control+K Meta+K"
          autoComplete="off"
          placeholder={placeholder}
          value={term}
          onChange={(event) => {
            setTerm(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        <kbd className="adm-kbd wo-search__hint" aria-hidden="true">
          /
        </kbd>
      </form>

      {open ? (
        <div className="wo-search__panel" id={listId} role="listbox" aria-label="Search results">
          <p className="wo-visually-hidden" role="status">
            {loading ? "Searching" : empty ? "No results" : searching ? `${groups.reduce((n, g) => n + g.hits.length, 0)} results` : ""}
          </p>
          {loading ? <p className="wo-search__note">Searching…</p> : null}
          {empty ? (
            <div className="wo-search__empty">
              <SearchX size={20} strokeWidth={1.5} aria-hidden="true" />
              <p>
                <strong>No results for “{term.trim()}”</strong>
                Check the spelling, use fewer words, or try one of these pages.
              </p>
            </div>
          ) : null}

          {rows.map((group) => {
            const headingId = `${base}-h-${group.id}`;
            return (
              <div key={group.id} role="group" aria-labelledby={group.label ? headingId : undefined} className="wo-search__group">
                {group.label ? (
                  <div className="wo-search__heading" id={headingId}>
                    <span>{group.label}</span>
                    {group.id === "recent" ? (
                      <button type="button" className="wo-linkbtn" onClick={() => clearRecents.mutate()}>
                        Clear
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {group.rows.map((row) => {
                  const index = flat.indexOf(row);
                  const current = index === active;
                  if (row.kind === "all") {
                    return (
                      <div key={row.id} id={row.id} role="option" aria-selected={current} className="wo-search__row wo-search__row--all" data-active={current} onPointerDown={(e) => e.preventDefault()} onClick={() => activate(row)} onPointerMove={() => setActive(index)}>
                        <CornerDownLeft size={18} strokeWidth={1.5} aria-hidden="true" />
                        <span>See all results for “{term.trim()}”</span>
                      </div>
                    );
                  }
                  if (row.kind === "recent") {
                    return (
                      <div key={row.id} id={row.id} role="option" aria-selected={current} className="wo-search__row" data-active={current} onPointerDown={(e) => e.preventDefault()} onClick={() => activate(row)} onPointerMove={() => setActive(index)}>
                        <Clock size={18} strokeWidth={1.5} aria-hidden="true" />
                        <span className="wo-search__main">{row.term}</span>
                      </div>
                    );
                  }
                  const Icon = iconOf(row.hit.type);
                  return (
                    <div key={row.id} id={row.id} role="option" aria-selected={current} aria-label={[row.hit.title, row.hit.subtitle, tagOf(row.hit.type)].filter(Boolean).join(", ")} className="wo-search__row" data-active={current} onPointerDown={(e) => e.preventDefault()} onClick={() => activate(row)} onPointerMove={() => setActive(index)}>
                      <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                      <span className="wo-search__main">
                        <span className="wo-search__title">
                          <Marked text={row.hit.title} term={term} />
                        </span>
                        {row.hit.subtitle ? (
                          <span className="wo-search__sub">
                            <Marked text={row.hit.subtitle} term={term} />
                          </span>
                        ) : null}
                      </span>
                      <span className="wo-search__tag">{tagOf(row.hit.type)}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
