import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Modal } from "../components";
import { useAuth } from "./AuthProvider";
import { IDLE_LIMIT_MS, IDLE_WARNING_MS, idleFor, markActive, noteIdleSignOut, staleOnLoad } from "./idle";

const ACTIVITY = ["pointerdown", "pointermove", "keydown", "wheel", "scroll", "touchstart"] as const;

/**
 * Signs a member or admin out after five minutes without activity, with a warning in the last
 * minute. Activity in any tab counts for all of them.
 */
export function IdleTimeout() {
  const { status, logout } = useAuth();
  const navigate = useNavigate();
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const signingOut = useRef(false);
  const checkedLoad = useRef(false);

  useEffect(() => {
    if (status !== "authenticated") {
      setSecondsLeft(null);
      signingOut.current = false;
      return;
    }

    const signOut = () => {
      if (signingOut.current) return;
      signingOut.current = true;
      noteIdleSignOut();
      setSecondsLeft(null);
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
      const idle = idleFor();
      if (idle >= IDLE_LIMIT_MS) signOut();
      else if (idle >= IDLE_LIMIT_MS - IDLE_WARNING_MS) setSecondsLeft(Math.ceil((IDLE_LIMIT_MS - idle) / 1000));
      else setSecondsLeft(null);
    }, 1_000);

    return () => {
      for (const name of ACTIVITY) window.removeEventListener(name, onActivity, { capture: true });
      window.clearInterval(tick);
    };
  }, [status, logout, navigate]);

  if (secondsLeft === null) return null;
  return (
    <Modal
      open
      onClose={() => markActive()}
      eyebrow="Still there?"
      title="You are about to be signed out"
      actions={<Button onClick={() => { markActive(); setSecondsLeft(null); }}>Stay signed in</Button>}
    >
      <p className="body" style={{ margin: 0 }} aria-live="polite">
        For your security, you will be signed out in {secondsLeft} {secondsLeft === 1 ? "second" : "seconds"} because nothing has happened for a while.
      </p>
    </Modal>
  );
}
