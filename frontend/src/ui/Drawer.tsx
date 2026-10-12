import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../components";
import "../styles/shared-ui.css";

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** One line under the title. */
  subtitle?: ReactNode;
  /** Shown above the title in small capitals, such as a ticket number. */
  eyebrow?: ReactNode;
  /** `md` is a form beside the page; `lg` is a wizard or a long record. Full width on a phone. */
  size?: "md" | "lg";
  /** Buttons pinned to the bottom. */
  footer?: ReactNode;
  /** Closing then asks before throwing away what was typed. */
  dirty?: boolean;
  /** Extra controls in the header, before the close button. */
  actions?: ReactNode;
  children: ReactNode;
}

/**
 * A panel that slides in from the right over a dimmed page. Focus is trapped inside, Esc and a click
 * outside close it, and when `dirty` is set they first ask whether to discard what was typed.
 */
export function Drawer({ open, onOpenChange, title, subtitle, eyebrow, size = "md", footer, dirty = false, actions, children }: DrawerProps) {
  const [asking, setAsking] = useState(false);
  const keep = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  // Remember what had focus before the drawer took it, so closing can give it back.
  useLayoutEffect(() => {
    if (open) opener.current = document.activeElement as HTMLElement | null;
  }, [open]);

  useEffect(() => {
    if (!open) setAsking(false);
  }, [open]);

  useEffect(() => {
    if (asking) keep.current?.focus();
  }, [asking]);

  const requestClose = () => {
    if (dirty) setAsking(true);
    else onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? onOpenChange(true) : requestClose())}>
      <Dialog.Portal>
        <Dialog.Overlay className="wo-drawer__scrim" />
        <Dialog.Content
          className="wo-drawer"
          data-size={size}
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            const back = opener.current;
            if (back && document.contains(back)) {
              event.preventDefault();
              back.focus();
            }
          }}
          // A toast is not "away from the drawer", so using it keeps the drawer open.
          onInteractOutside={(event) => {
            if ((event.target as HTMLElement | null)?.closest?.(".app-toasts")) event.preventDefault();
          }}
        >
          <header className="wo-drawer__head">
            <div className="wo-drawer__titles">
              {eyebrow ? <p className="wo-drawer__eyebrow">{eyebrow}</p> : null}
              <Dialog.Title className="wo-drawer__title">{title}</Dialog.Title>
              {subtitle ? <p className="wo-drawer__subtitle">{subtitle}</p> : null}
            </div>
            <div className="wo-drawer__tools">
              {actions}
              <Dialog.Close className="wo-drawer__close" aria-label="Close">
                <X size={18} strokeWidth={1.5} aria-hidden="true" />
              </Dialog.Close>
            </div>
          </header>

          {/* A box that scrolls must be focusable so keyboard users can scroll it. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="wo-drawer__body" tabIndex={0} role="region" aria-label={title}>
            {children}
          </div>

          {asking ? (
            <footer className="wo-drawer__foot" role="alertdialog" aria-label="Discard your changes?">
              <p className="wo-drawer__ask">Discard what you have typed?</p>
              <div className="wo-drawer__actions">
                <Button ref={keep} variant="secondary" onClick={() => setAsking(false)}>
                  Keep editing
                </Button>
                <Button variant="danger" onClick={() => onOpenChange(false)}>
                  Discard
                </Button>
              </div>
            </footer>
          ) : footer ? (
            <footer className="wo-drawer__foot">
              <div className="wo-drawer__actions">{footer}</div>
            </footer>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
