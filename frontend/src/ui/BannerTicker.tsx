import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Info, Megaphone, Pause, Play, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import "../styles/banner.css";

export interface TickerItem {
  id: string;
  kind: "announcement" | "news" | "urgent";
  text: string;
  link: string;
}

const LABEL: Record<TickerItem["kind"], string> = { announcement: "Announcement", news: "News", urgent: "Urgent" };
const ICON = { announcement: Megaphone, news: Info, urgent: AlertTriangle };

/** True when the person has asked their device for less motion. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

function ItemLink({ item, decorative }: { item: TickerItem; decorative?: boolean }) {
  const Icon = ICON[item.kind];
  const inner = (
    <>
      <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
      <strong>{LABEL[item.kind]}:</strong> {item.text}
    </>
  );
  const props = { className: "wo-ticker__link", "data-kind": item.kind, ...(decorative ? { tabIndex: -1 } : {}) };
  if (item.link.startsWith("/")) return <Link to={item.link.startsWith("/app") ? item.link : `/app${item.link}`} {...props}>{inner}</Link>;
  return <a href={item.link} target="_blank" rel="noopener noreferrer" {...props}>{inner}</a>;
}

/**
 * The scrolling line of announcements and news. It is a plain list for a screen reader, pauses when
 * the pointer or focus is on it (or the Pause button is pressed), and with reduced motion it stops
 * moving and shows one item at a time with Previous and Next.
 */
export function TickerView({ items, onDismiss, preview = false }: { items: TickerItem[]; onDismiss?: () => void; preview?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const [paused, setPaused] = useState(false);
  const [index, setIndex] = useState(0);
  const current = items[Math.min(index, items.length - 1)];
  if (!current) return null;
  const seconds = Math.max(18, items.reduce((n, i) => n + i.text.length, 0) * 0.35);
  return (
    <section className="wo-ticker" aria-label="Announcements and news" data-urgent={items.some((i) => i.kind === "urgent") || undefined} data-paused={paused || undefined}>
      <div className="wo-ticker__controls">
        {reduced ? (
          <>
            <button type="button" className="wo-ticker__btn" aria-label="Previous announcement" disabled={index <= 0} onClick={() => setIndex((i) => Math.max(0, i - 1))}><ChevronLeft size={16} aria-hidden="true" /></button>
            <span className="wo-ticker__count" aria-live="polite">{Math.min(index, items.length - 1) + 1} of {items.length}</span>
            <button type="button" className="wo-ticker__btn" aria-label="Next announcement" disabled={index >= items.length - 1} onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}><ChevronRight size={16} aria-hidden="true" /></button>
          </>
        ) : (
          <button type="button" className="wo-ticker__btn" aria-label={paused ? "Play the moving announcements" : "Pause the moving announcements"} aria-pressed={paused} onClick={() => setPaused((p) => !p)}>
            {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
          </button>
        )}
      </div>
      {reduced ? (
        <ul className="wo-ticker__list wo-ticker__list--still">
          <li><ItemLink item={current} /></li>
        </ul>
      ) : (
        <div className="wo-ticker__window">
          <div className="wo-ticker__track" style={{ animationDuration: `${seconds}s` }}>
            <ul className="wo-ticker__list">
              {items.map((i) => <li key={i.id}><ItemLink item={i} /></li>)}
            </ul>
            <ul className="wo-ticker__list" aria-hidden="true">
              {items.map((i) => <li key={i.id}><ItemLink item={i} decorative /></li>)}
            </ul>
          </div>
        </div>
      )}
      {onDismiss && !preview ? (
        <button type="button" className="wo-ticker__btn" aria-label="Close announcements" onClick={onDismiss}><X size={16} aria-hidden="true" /></button>
      ) : null}
    </section>
  );
}

/** The banner at the top of the member dashboard. It checks for changes about once a minute. */
export function BannerTicker() {
  const client = useQueryClient();
  const banners = useQuery({
    queryKey: ["banners"],
    queryFn: () => unwrap(api.GET("/api/v1/banners")),
    refetchInterval: 60_000,
    staleTime: 60_000,
  });
  const [closed, setClosed] = useState(false);
  const items: TickerItem[] = (banners.data ?? []).map((b) => ({ id: b.id, kind: b.kind, text: b.text, link: b.link }));
  if (closed || items.length === 0) return null;
  const dismiss = async () => {
    setClosed(true);
    await Promise.all(items.map((i) => api.POST("/api/v1/banners/{item_id}/dismiss", { params: { path: { item_id: i.id } } })));
    await client.invalidateQueries({ queryKey: ["banners"] });
  };
  return <TickerView items={items} onDismiss={() => void dismiss()} />;
}
