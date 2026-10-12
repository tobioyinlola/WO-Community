import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronLeft, ChevronRight, Columns3, Rows3, Rows4, X } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { Button } from "../../components";
import { formatNumber } from "../../lib/format";

export type Tone = "success" | "warning" | "danger" | "neutral" | "info";

/** A status as a dot and a word, so it never depends on colour alone. */
export function StatusChip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className="adm-status" data-tone={tone}>
      <i aria-hidden="true" />
      {children}
    </span>
  );
}

/** A small bar with its number beside it. The tone follows the value unless one is given. */
export function MeterBar({ value, label, max = 100 }: { value: number; label: string; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tone = pct >= 70 ? "success" : pct >= 40 ? "warning" : "danger";
  return (
    <span className="adm-meter" data-tone={tone}>
      <span className="adm-meter__bar" role="meter" aria-label={label} aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max}>
        <span style={{ width: `${pct}%` }} />
      </span>
      <span className="adm-meter__num">{Math.round(value)}</span>
    </span>
  );
}

export interface Chip {
  id: string;
  label: string;
  onRemove: () => void;
}

/** The filters in force, each removable, with a way to drop them all. */
export function FilterChips({ chips, onClear }: { chips: Chip[]; onClear: () => void }) {
  if (chips.length === 0) return null;
  return (
    <ul className="adm-chips" aria-label="Filters in use">
      {chips.map((chip) => (
        <li key={chip.id}>
          <span className="adm-fchip">
            {chip.label}
            <button type="button" className="adm-fchip__x" onClick={chip.onRemove} aria-label={`Remove filter ${chip.label}`}>
              <X size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </span>
        </li>
      ))}
      <li>
        <button type="button" className="adm-linkbtn" onClick={onClear}>Clear all</button>
      </li>
    </ul>
  );
}

/** A row of large figures with small labels. */
export function StatStrip({ items, loading = false, columns }: { items: Array<{ label: string; value: string }>; loading?: boolean; columns?: number }) {
  return (
    <dl className="adm-card adm-strip" aria-label="Summary" style={columns ? ({ "--adm-cols": columns } as CSSProperties) : undefined}>
      {items.map((item) => (
        <div key={item.label} className="adm-strip__item">
          <dd>{loading ? "…" : item.value}</dd>
          <dt>{item.label}</dt>
        </div>
      ))}
    </dl>
  );
}

/** Slides up from the bottom while rows are selected. */
export function BulkBar({ count, noun = "selected", onClear, children }: { count: number; noun?: string; onClear: () => void; children: ReactNode }) {
  if (count === 0) return null;
  return (
    <div className="adm-bulk" role="region" aria-label="Actions for the selected rows">
      <span className="adm-bulk__count">{formatNumber(count)} {noun}</span>
      <div className="adm-bulk__actions">{children}</div>
      <Button variant="ghost" size="sm" onClick={onClear}>Clear selection</Button>
    </div>
  );
}

const SIZES = [25, 50, 100];

/** Page size, the range on show and previous or next. */
export function Pager({ page, size, total, onPage, onSize, sizes = SIZES }: { page: number; size: number; total: number; onPage: (page: number) => void; onSize: (size: number) => void; sizes?: number[] }) {
  const first = total === 0 ? 0 : page * size + 1;
  const last = Math.min(total, (page + 1) * size);
  return (
    <div className="adm-pager">
      <label className="adm-pager__size">
        <span>Rows per page</span>
        <select value={size} onChange={(e) => onSize(Number(e.target.value))}>
          {sizes.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <p className="adm-pager__range" role="status">
        {formatNumber(first)}–{formatNumber(last)} of {formatNumber(total)}
      </p>
      <div className="adm-pager__nav">
        <button type="button" className="adm-iconbtn adm-iconbtn--ring" onClick={() => onPage(page - 1)} disabled={page <= 0} aria-label="Previous page">
          <ChevronLeft size={18} strokeWidth={1.5} aria-hidden="true" />
        </button>
        <button type="button" className="adm-iconbtn adm-iconbtn--ring" onClick={() => onPage(page + 1)} disabled={last >= total} aria-label="Next page">
          <ChevronRight size={18} strokeWidth={1.5} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export interface ColumnChoice {
  id: string;
  label: string;
  visible: boolean;
  /** A column that cannot be hidden, such as the first. */
  locked?: boolean;
}

/** The Columns menu: tick what to show. */
export function ColumnsMenu({ columns, onToggle, onReset }: { columns: ColumnChoice[]; onToggle: (id: string) => void; onReset: () => void }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="secondary" icon={<Columns3 size={16} strokeWidth={1.5} aria-hidden="true" />}>Columns</Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={8} className="adm-menu">
          <DropdownMenu.Label className="adm-menu__label">Show columns</DropdownMenu.Label>
          {columns.map((c) => (
            <DropdownMenu.CheckboxItem
              key={c.id}
              className="adm-menu__item adm-menu__radio"
              checked={c.visible}
              disabled={c.locked}
              onSelect={(e) => {
                e.preventDefault();
                onToggle(c.id);
              }}
            >
              <span className="adm-check" aria-hidden="true"><DropdownMenu.ItemIndicator>{"✓"}</DropdownMenu.ItemIndicator></span>
              <span>{c.label}</span>
            </DropdownMenu.CheckboxItem>
          ))}
          <DropdownMenu.Separator className="adm-menu__sep" />
          <DropdownMenu.Item className="adm-menu__item" onSelect={onReset}>Show all</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export type Density = "comfortable" | "compact";

/** Comfortable rows are 56px high, compact ones 44px. */
export function DensityToggle({ value, onChange }: { value: Density; onChange: (next: Density) => void }) {
  return (
    <div className="adm-iconpair" role="group" aria-label="Row height">
      <button type="button" className="adm-iconbtn" aria-pressed={value === "comfortable"} aria-label="Comfortable rows" onClick={() => onChange("comfortable")}>
        <Rows3 size={18} strokeWidth={1.5} aria-hidden="true" />
      </button>
      <button type="button" className="adm-iconbtn" aria-pressed={value === "compact"} aria-label="Compact rows" onClick={() => onChange("compact")}>
        <Rows4 size={18} strokeWidth={1.5} aria-hidden="true" />
      </button>
    </div>
  );
}
