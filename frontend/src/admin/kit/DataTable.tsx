import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { Skeleton } from "../../ui/blocks";
import type { Density } from "./TableBits";

export interface Sort {
  id: string;
  desc: boolean;
}

/** What a column can say about itself, beyond what the table library needs. */
export interface ColumnMeta {
  /** The name the server sorts this column by. Without one the column is not sortable. */
  sortKey?: string;
  align?: "end";
  /** A plain name for the Columns menu and the screen reader. */
  label?: string;
}

interface DataTableProps<T> {
  columns: Array<ColumnDef<T, unknown>>;
  data: T[];
  getRowId: (row: T) => string;
  caption: string;
  sort?: Sort;
  onSortChange?: (next: Sort) => void;
  /** Row ids ticked. Leave undefined for a table with no tick boxes. */
  selected?: Set<string>;
  onSelectedChange?: (next: Set<string>) => void;
  visibility?: Record<string, boolean>;
  density?: Density;
  loading?: boolean;
  /** Shown instead of the table when there are no rows. */
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  /** The row the keyboard is on, drawn with a highlight. */
  activeRowId?: string | null;
  /** A short name for a row, used to label its tick box. */
  rowLabel?: (row: T) => string;
}

const metaOf = (column: { columnDef: { meta?: unknown } }) => (column.columnDef.meta ?? {}) as ColumnMeta;

/**
 * A sortable, selectable table with a sticky header and a pinned first column. Sorting is done by
 * the server, so the table only reports what was asked for and shows what came back.
 */
export function DataTable<T>({ columns, data, getRowId, caption, sort, onSortChange, selected, onSelectedChange, visibility, density = "comfortable", loading = false, empty, onRowClick, activeRowId, rowLabel }: DataTableProps<T>) {
  const table = useReactTable({
    data,
    columns,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    state: { columnVisibility: visibility ?? {} },
    manualSorting: true,
  });
  const rows = table.getRowModel().rows;
  const ids = rows.map((r) => r.id);
  const allOn = selected !== undefined && ids.length > 0 && ids.every((id) => selected.has(id));
  const someOn = selected !== undefined && ids.some((id) => selected.has(id)) && !allOn;

  const toggleAll = () => {
    if (!selected || !onSelectedChange) return;
    const next = new Set(selected);
    for (const id of ids) {
      if (allOn) next.delete(id);
      else next.add(id);
    }
    onSelectedChange(next);
  };
  const toggleRow = (id: string) => {
    if (!selected || !onSelectedChange) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  };
  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" && onRowClick) onRowClick(row);
  };

  if (!loading && rows.length === 0 && empty) return <>{empty}</>;

  return (
    // A box that scrolls must be focusable so keyboard users can scroll it.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className="adm-tablewrap" data-density={density} role="region" aria-label={`${caption}, scrolls sideways on a small screen`} tabIndex={0}>
      <table className="adm-table">
        <caption className="wo-visually-hidden">{caption}</caption>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {selected ? (
                <th scope="col" className="adm-table__select">
                  <input type="checkbox" checked={allOn} ref={(el) => { if (el) el.indeterminate = someOn; }} onChange={toggleAll} aria-label="Select every row on this page" />
                </th>
              ) : null}
              {group.headers.map((header, index) => {
                const meta = metaOf(header.column);
                const key = meta.sortKey;
                const active = key !== undefined && sort?.id === key;
                return (
                  <th
                    key={header.id}
                    scope="col"
                    data-align={meta.align}
                    data-pinned={index === 0}
                    aria-sort={active ? (sort?.desc ? "descending" : "ascending") : key ? "none" : undefined}
                  >
                    {header.isPlaceholder ? null : key && onSortChange ? (
                      <button type="button" className="adm-sortbtn" onClick={() => onSortChange({ id: key, desc: active ? !sort?.desc : false })}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {active ? (sort?.desc ? <ArrowDown size={14} strokeWidth={2} aria-hidden="true" /> : <ArrowUp size={14} strokeWidth={2} aria-hidden="true" />) : <ArrowUpDown size={14} strokeWidth={1.5} aria-hidden="true" />}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 6 }, (_, i) => (
                <tr key={i}>
                  {selected ? <td /> : null}
                  {table.getVisibleLeafColumns().map((c) => (
                    <td key={c.id}><Skeleton width="70%" height={14} /></td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={row.id}
                  data-selected={selected?.has(row.id) || undefined}
                  data-active={activeRowId === row.id || undefined}
                  data-clickable={onRowClick ? true : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? (e) => { if (!(e.target as HTMLElement).closest("button, a, input, label")) onRowClick(row.original); } : undefined}
                  onKeyDown={onRowClick ? (e) => onRowKey(e, row.original) : undefined}
                >
                  {selected ? (
                    <td className="adm-table__select">
                      <input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleRow(row.id)} aria-label={`Select ${rowLabel ? rowLabel(row.original) : "this row"}`} />
                    </td>
                  ) : null}
                  {row.getVisibleCells().map((cell, index) => {
                    const meta = metaOf(cell.column);
                    return index === 0 ? (
                      <th key={cell.id} scope="row" data-pinned="true" data-align={meta.align}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </th>
                    ) : (
                      <td key={cell.id} data-align={meta.align}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    );
                  })}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
