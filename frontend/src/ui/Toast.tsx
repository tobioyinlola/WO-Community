import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  text: string;
  action?: ToastAction;
}

interface ToastOptions {
  /** A button on the toast, such as Undo. Pressing it also closes the toast. */
  action?: ToastAction;
  /** How long it stays, in milliseconds. */
  duration?: number;
}

interface ToastApi {
  /** A short confirmation that disappears by itself. */
  show: (text: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
const LIFETIME_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const close = useCallback((id: number) => setItems((current) => current.filter((t) => t.id !== id)), []);

  const show = useCallback(
    (text: string, options: ToastOptions = {}) => {
      const id = next.current++;
      setItems((current) => [...current.slice(-2), { id, text, action: options.action }]);
      window.setTimeout(() => close(id), options.duration ?? LIFETIME_MS);
    },
    [close],
  );

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="app-toasts" role="status" aria-live="polite">
        {items.map((item) => (
          <div className="app-toast" key={item.id}>
            <span aria-hidden="true">{"✓"}</span>
            <span>{item.text}</span>
            {item.action ? (
              <button
                type="button"
                className="app-toast__action"
                onClick={() => {
                  item.action?.onClick();
                  close(item.id);
                }}
              >
                {item.action.label}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (value === null) throw new Error("useToast must be used inside a ToastProvider");
  return value;
}
