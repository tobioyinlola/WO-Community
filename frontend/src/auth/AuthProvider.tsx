import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, refreshSession, unwrap } from "../api/client";
import { setAccessToken } from "../api/session";
import { clearIdleSignOutNote, markActive } from "./idle";
import type { components } from "../api/schema";

export type Me = components["schemas"]["Me"];

export type AuthStatus = "loading" | "anonymous" | "authenticated";

/** What a sign-in produced: a session, or a second step that still needs a code. */
export type LoginOutcome = { kind: "signed-in" } | { kind: "mfa"; mfaToken: string };

interface AuthContextValue {
  status: AuthStatus;
  me: Me | null;
  /** The member is signed in but an admin has not approved them yet. */
  isPending: boolean;
  login: (email: string, password: string) => Promise<LoginOutcome>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function loadMe(): Promise<Me> {
  return unwrap(api.GET("/api/v1/me"));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const started = useRef(false);

  const settle = useCallback(async () => {
    try {
      setMe(await loadMe());
      setStatus("authenticated");
    } catch {
      setAccessToken(null);
      setMe(null);
      setStatus("anonymous");
    }
  }, []);

  // On first load, trade the refresh cookie for an access token if there is one.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      if (await refreshSession()) await settle();
      else setStatus("anonymous");
    })();
  }, [settle]);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginOutcome> => {
      const { data, response, error } = await api.POST("/api/v1/auth/login", {
        body: { email, password },
      });
      if (response.status === 202) {
        const challenge = data as unknown as { mfa_token: string };
        return { kind: "mfa", mfaToken: challenge.mfa_token };
      }
      if (!response.ok || !data || !("access_token" in data)) {
        // Hand the failure to the shared error path so forms show the server's own words.
        await unwrap(Promise.resolve({ error, response }));
        throw new Error("Sign in failed");
      }
      setAccessToken(data.access_token);
      markActive(); // a fresh sign-in starts the inactivity clock again
      clearIdleSignOutNote();
      await settle();
      return { kind: "signed-in" };
    },
    [settle],
  );

  const verifyMfa = useCallback(
    async (mfaToken: string, code: string) => {
      const data = await unwrap(
        api.POST("/api/v1/auth/mfa/verify", { body: { mfa_token: mfaToken, code } }),
      );
      setAccessToken(data.access_token);
      markActive();
      clearIdleSignOutNote();
      await settle();
    },
    [settle],
  );

  const logout = useCallback(async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      setAccessToken(null);
      setMe(null);
      setStatus("anonymous");
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      isPending: me?.status === "pending",
      login,
      verifyMfa,
      logout,
      refreshMe: settle,
    }),
    [status, me, login, verifyMfa, logout, settle],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside an AuthProvider");
  return value;
}
