import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { IDLE_LIMIT_MS, idleFor, markActive, noteIdleSignOut, staleOnLoad } from "./idle";

const ACTIVITY = ["pointerdown", "pointermove", "keydown", "wheel", "scroll", "touchstart"] as const;

/** Signs a member or admin out after five minutes without activity. Activity in any tab counts. */
export function IdleTimeout() {
  const { status, logout } = useAuth();
  const navigate = useNavigate();
  const signingOut = useRef(false);
  const checkedLoad = useRef(false);

  useEffect(() => {
    if (status !== "authenticated") {
      signingOut.current = false;
      return;
    }

    const signOut = () => {
      if (signingOut.current) return;
      signingOut.current = true;
      noteIdleSignOut();
      navigate("/login", { replace: true });
      void logout();
    };

    if (!checkedLoad.current) {
      checkedLoad.current = true;
      if (staleOnLoad()) {
        signOut();
        return;
      }
    }
    markActive();

    let lastMark = 0;
    const onActivity = () => {
      const now = Date.now();
      if (now - lastMark < 2_000) return; // a mark every couple of seconds is plenty
      lastMark = now;
      markActive(now);
    };
    for (const name of ACTIVITY) window.addEventListener(name, onActivity, { passive: true, capture: true });

    const tick = window.setInterval(() => {
      if (idleFor() >= IDLE_LIMIT_MS) signOut();
    }, 1_000);

    return () => {
      for (const name of ACTIVITY) window.removeEventListener(name, onActivity, { capture: true });
      window.clearInterval(tick);
    };
  }, [status, logout, navigate]);

  return null;
}
