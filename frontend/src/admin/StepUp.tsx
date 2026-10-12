import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { api, unwrap } from "../api/client";
import { ApiError } from "../api/errors";
import { setAccessToken } from "../api/session";
import { Button, Input, Modal } from "../components";
import { FormError, useSubmit } from "../ui/forms";

type Guard = <T>(action: () => Promise<T>) => Promise<T>;

const StepUpContext = createContext<Guard | null>(null);

/**
 * Sensitive actions ask for a fresh code from the authenticator app. Wrap the call in `guard`:
 * if the server asks for one, a dialog collects it and the call is tried again once.
 */
export function StepUpProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const waiting = useRef<{ done: () => void; cancel: () => void } | null>(null);

  const ask = useCallback(
    () =>
      new Promise<void>((done, cancel) => {
        waiting.current = { done, cancel: () => cancel(new Error("cancelled")) };
        setCode("");
        setOpen(true);
      }),
    [],
  );

  const guard = useCallback<Guard>(
    async (action) => {
      try {
        return await action();
      } catch (error) {
        if (!(error instanceof ApiError) || error.code !== "step_up_required") throw error;
        await ask();
        return action();
      }
    },
    [ask],
  );

  const confirm = useSubmit(async () => {
    const data = await unwrap(api.POST("/api/v1/auth/mfa/step-up", { body: { code: code.trim() } }));
    setAccessToken(data.access_token);
    setOpen(false);
    waiting.current?.done();
  });

  const close = () => {
    setOpen(false);
    waiting.current?.cancel();
  };

  const value = useMemo(() => guard, [guard]);
  return (
    <StepUpContext.Provider value={value}>
      {children}
      {open ? (
        <Modal
          open
          onClose={close}
          eyebrow="Security check"
          title="Confirm it is you"
          actions={
            <>
              <Button variant="ghost" onClick={close}>Cancel</Button>
              <Button loading={confirm.busy} disabled={code.trim().length < 6} onClick={() => void confirm.run()}>Confirm</Button>
            </>
          }
        >
          <form className="app-stack" onSubmit={(e) => { e.preventDefault(); if (code.trim().length >= 6) void confirm.run(); }}>
            <p className="body" style={{ margin: 0 }}>This action needs a fresh code. Open your authenticator app and enter the 6 digit code.</p>
            <FormError error={confirm.error} />
            <Input label="Authenticator code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
          </form>
        </Modal>
      ) : null}
    </StepUpContext.Provider>
  );
}

export function useStepUp(): Guard {
  const guard = useContext(StepUpContext);
  if (!guard) throw new Error("useStepUp must be used inside a StepUpProvider");
  return guard;
}
