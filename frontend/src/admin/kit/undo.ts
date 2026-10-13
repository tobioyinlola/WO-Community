import { useCallback } from "react";
import { useToast } from "../../ui/Toast";

export const UNDO_MS = 8000;

/**
 * Approvals and rejections cannot be taken back once the member has been told, so they are held for
 * a few seconds with an Undo button and only then sent. The hold lives in the browser: closing the
 * tab inside the window drops the action instead of sending it.
 */
export function useUndoable() {
  const toast = useToast();
  return useCallback(
    ({ message, commit, onUndo }: { message: string; commit: () => Promise<unknown> | void; onUndo?: () => void }) => {
      let cancelled = false;
      const timer = window.setTimeout(() => {
        if (!cancelled) void commit();
      }, UNDO_MS);
      toast.show(message, {
        duration: UNDO_MS,
        action: {
          label: "Undo",
          onClick: () => {
            cancelled = true;
            window.clearTimeout(timer);
            onUndo?.();
          },
        },
      });
    },
    [toast],
  );
}
