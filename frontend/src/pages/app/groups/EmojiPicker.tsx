import { useEffect, useRef, useState } from "react";
import { EMOJI_SETS } from "./emoji";

/**
 * A small panel of emoji in tabs. It closes when an emoji is picked (unless `stayOpen`), on Escape,
 * or on a click outside it.
 */
export function EmojiPicker({
  onPick,
  onClose,
  stayOpen = false,
  label = "Choose an emoji",
  align = "start",
}: {
  onPick: (emoji: string) => void;
  onClose: () => void;
  stayOpen?: boolean;
  label?: string;
  align?: "start" | "end";
}) {
  const [tab, setTab] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    // Wait a tick so the click that opened the panel does not close it again.
    const timer = window.setTimeout(() => document.addEventListener("pointerdown", away), 0);
    document.addEventListener("keydown", escape);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [onClose]);

  const set = EMOJI_SETS[tab] ?? EMOJI_SETS[0]!;
  return (
    <div ref={ref} className={`wo-emoji wo-emoji--${align}`} role="dialog" aria-label={label}>
      <div className="wo-emoji__tabs" role="tablist" aria-label="Emoji groups">
        {EMOJI_SETS.map((s, i) => (
          <button
            key={s.label}
            type="button"
            role="tab"
            aria-selected={i === tab}
            title={s.label}
            aria-label={s.label}
            className="wo-emoji__tab"
            onClick={() => setTab(i)}
          >
            {s.icon}
          </button>
        ))}
      </div>
      <p className="wo-emoji__title">{set.label}</p>
      <div className="wo-emoji__grid">
        {set.emoji.map((e) => (
          <button
            key={e}
            type="button"
            className="wo-emoji__item"
            aria-label={e}
            onClick={() => {
              onPick(e);
              if (!stayOpen) onClose();
            }}
          >
            {e}
          </button>
        ))}
      </div>
    </div>
  );
}
