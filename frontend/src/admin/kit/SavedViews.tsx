import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bookmark, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, Input, Modal } from "../../components";
import { usePref } from "../shell/prefs";

interface View {
  name: string;
  /** The page's own search string, without the page number. */
  query: string;
}

/**
 * Named filter sets kept in this browser. A view is just the address a filtered list had, so
 * applying one is the same as following a link to it.
 */
export function SavedViews({ storageKey, currentQuery, onApply }: { storageKey: string; currentQuery: string; onApply: (query: string) => void }) {
  const [views, setViews] = usePref<View[]>(`views:${storageKey}`, []);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const save = () => {
    const clean = name.trim();
    if (!clean) return;
    setViews((current) => [...current.filter((v) => v.name !== clean), { name: clean, query: currentQuery }]);
    setName("");
    setNaming(false);
  };
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button variant="secondary" icon={<Bookmark size={16} strokeWidth={1.5} aria-hidden="true" />}>Views</Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={8} className="adm-menu">
            <DropdownMenu.Label className="adm-menu__label">Saved views</DropdownMenu.Label>
            {views.length === 0 ? <p className="adm-menu__empty">None yet. Set the filters you want, then save them here.</p> : null}
            {views.map((view) => (
              <div key={view.name} className="adm-menu__row">
                <DropdownMenu.Item className="adm-menu__item adm-menu__grow" onSelect={() => onApply(view.query)}>{view.name}</DropdownMenu.Item>
                <DropdownMenu.Item className="adm-menu__item adm-menu__icon" aria-label={`Delete the view ${view.name}`} onSelect={() => setViews((current) => current.filter((v) => v.name !== view.name))}>
                  <Trash2 size={16} strokeWidth={1.5} aria-hidden="true" />
                </DropdownMenu.Item>
              </div>
            ))}
            <DropdownMenu.Separator className="adm-menu__sep" />
            <DropdownMenu.Item className="adm-menu__item" onSelect={() => setNaming(true)}>Save the current filters…</DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {naming ? (
        <Modal
          open
          onClose={() => setNaming(false)}
          eyebrow="Views"
          title="Save this view"
          actions={
            <>
              <Button variant="ghost" onClick={() => setNaming(false)}>Cancel</Button>
              <Button disabled={!name.trim()} onClick={save}>Save view</Button>
            </>
          }
        >
          <form className="app-stack" onSubmit={(e) => { e.preventDefault(); save(); }}>
            <Input label="Name" hint="For example: waiting for approval in Nigeria" value={name} onChange={(e) => setName(e.target.value)} />
          </form>
        </Modal>
      ) : null}
    </>
  );
}
