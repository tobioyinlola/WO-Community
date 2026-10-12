import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  text: string;
}

interface ToastApi {
  /** A short confirmation that disappears by itself. */
  show: (text: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
const LIFETIME_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const show = useCallback((text: string) => {
    const id = next.current++;
    setItems((current) => [...current.slice(-2), { id, text }]);
    window.setTimeout(() => setItems((current) => current.filter((t) => t.id !== id)), LIFETIME_MS);
  }, []);

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="app-toasts" role="status" aria-live="polite">
        {items.map((item) => (
          <div className="app-toast" key={item.id}>
            <span aria-hidden="true">{"✓"}</span>
            <span>{item.text}</span>
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
