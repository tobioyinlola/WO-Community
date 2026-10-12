import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

const GROUPS: Array<{ title: string; rows: Array<{ keys: string[]; what: string }> }> = [
  {
    title: "Anywhere",
    rows: [
      { keys: ["Ctrl", "K"], what: "Open search and quick actions (Cmd K on a Mac)" },
      { keys: ["["], what: "Collapse or expand the sidebar" },
      { keys: ["?"], what: "Show this list" },
      { keys: ["Esc"], what: "Close a panel or dialog" },
    ],
  },
  {
    title: "In a list",
    rows: [
      { keys: ["J"], what: "Next row" },
      { keys: ["K"], what: "Previous row" },
      { keys: ["Enter"], what: "Open the highlighted row" },
    ],
  },
  {
    title: "In a request",
    rows: [
      { keys: ["A"], what: "Approve (asks you to confirm)" },
      { keys: ["R"], what: "Reject (asks for a reason)" },
      { keys: ["J"], what: "Next request" },
      { keys: ["K"], what: "Previous request" },
    ],
  },
];

export function Shortcuts({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="adm-scrim" />
        <Dialog.Content className="adm-dialog" aria-describedby={undefined}>
          <div className="adm-dialog__head">
            <Dialog.Title className="adm-dialog__title">Keyboard shortcuts</Dialog.Title>
            <Dialog.Close className="adm-iconbtn" aria-label="Close">
              <X size={20} strokeWidth={1.5} aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="adm-dialog__body">
            {GROUPS.map((group) => (
              <section key={group.title} aria-label={group.title}>
                <h3 className="adm-dialog__group">{group.title}</h3>
                <dl className="adm-keys">
                  {group.rows.map((row) => (
                    <div key={row.what} className="adm-keys__row">
                      <dt>
                        {row.keys.map((k) => (
                          <kbd key={k} className="adm-kbd">{k}</kbd>
                        ))}
                      </dt>
                      <dd>{row.what}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
