import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../lib/cx";

export interface TabItem {
  id: string;
  label: string;
  /** The content of the tab's panel. Leave out when the tabs only filter something else. */
  panel?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  /** `underline` for sections of a page; `segment` for compact filters. */
  variant?: "underline" | "segment";
  /** Accessible name for the tab list. */
  label: string;
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
}

/** Peer views of one object. Arrow keys, Home and End move between tabs. */
export function Tabs({
  items,
  variant = "underline",
  label,
  value,
  defaultValue,
  onChange,
}: TabsProps) {
  const base = useId();
  const [inner, setInner] = useState(defaultValue ?? items[0]?.id ?? "");
  const current = value ?? inner;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const select = (id: string, focusIndex?: number) => {
    if (value === undefined) setInner(id);
    onChange?.(id);
    if (focusIndex !== undefined) refs.current[focusIndex]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const last = items.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowRight") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    if (next === null) return;
    event.preventDefault();
    const target = items[next];
    if (target) select(target.id, next);
  };

  return (
    <div>
      <div
        role="tablist"
        aria-label={label}
        className={variant === "segment" ? "wo-segment" : "wo-tabs"}
      >
        {items.map((item, index) => {
          const selected = item.id === current;
          return (
            <button
              key={item.id}
              ref={(node) => {
                refs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={item.panel !== undefined ? `${base}-panel-${item.id}` : undefined}
              tabIndex={selected ? 0 : -1}
              className={cx("wo-tab")}
              onClick={() => select(item.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) =>
        item.panel !== undefined ? (
          <div
            key={item.id}
            role="tabpanel"
            id={`${base}-panel-${item.id}`}
            aria-labelledby={`${base}-tab-${item.id}`}
            hidden={item.id !== current}
            tabIndex={0}
          >
            {item.panel}
          </div>
        ) : null,
      )}
    </div>
  );
}
