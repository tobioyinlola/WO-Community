import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { getAccessToken, onTokenChange } from "../api/session";
import { useAuth } from "../auth/AuthProvider";
import "../styles/admin.css";
import "../styles/admin-kit.css";
import "../styles/admin-table.css";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { mfaAgeSeconds } from "./claims";
import MfaSetup from "./MfaSetup";
import { isAdmin, permissionsFor } from "./permissions";
import { CommandPalette } from "./shell/CommandPalette";
import { flatNav, visibleNav } from "./shell/nav";
import { isTyping, useMediaQuery, usePref } from "./shell/prefs";
import { Shortcuts } from "./shell/Shortcuts";
import { Sidebar, type Counts } from "./shell/Sidebar";
import { TopBar } from "./shell/TopBar";
import { StepUpProvider } from "./StepUp";

/** The first section a person may open, used when they land on the console. */
export function firstAllowed(roles: readonly string[]): string {
  const have = permissionsFor(roles);
  return flatNav(have).find((p) => !p.soon)?.to ?? "/admin/settings";
}

const ROLE_ORDER = ["super_admin", "community_admin", "content_editor"];

function nameFrom(email: string | undefined): string {
  const local = (email ?? "Admin").split("@")[0] ?? "Admin";
  return local.charAt(0).toUpperCase() + local.slice(1);
}

/**
 * The console frame: a floating sidebar that collapses to a rail, a floating top bar and the page.
 * Admin accounts must have passed a second step before anything opens.
 */
export function AdminLayout() {
  const { me } = useAuth();
  const location = useLocation();
  const narrow = useMediaQuery("(max-width: 1023px)");
  const [collapsed, setCollapsed] = usePref("sidebar-collapsed", false);
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [settingUp, setSettingUp] = useState(false);
  // Re-read the session whenever the token changes (after enrolling or a step up check).
  useSyncExternalStore(onTokenChange as (cb: () => void) => () => void, getAccessToken);

  const roles = useMemo(() => me?.roles ?? [], [me?.roles]);
  const have = useMemo(() => permissionsFor(roles), [roles]);
  const verified = mfaAgeSeconds() !== null;
  const ready = verified && !settingUp;

  const queues = useQuery({
    queryKey: ["admin", "queues"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/queues")),
    enabled: isAdmin(roles) && verified && have.has("dashboard.view"),
    refetchInterval: 60_000,
  });
  const counts: Counts = queues.data ?? {};

  useEffect(() => setDrawer(false), [location.pathname, location.search]);

  useEffect(() => {
    if (!ready) return;
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
        return;
      }
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "[") setCollapsed((c) => !c);
      else if (event.key === "?") setHelp(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready, setCollapsed]);

  if (!isAdmin(roles)) return <Navigate to="/app" replace />;

  const topRole = ROLE_ORDER.find((r) => roles.includes(r)) ?? "content_editor";
  const name = nameFrom(me?.email);
  const entries = visibleNav(have);
  const sidebar = (inDrawer: boolean) => (
    <Sidebar
      entries={entries}
      counts={counts}
      collapsed={inDrawer ? false : collapsed}
      onToggle={() => (inDrawer ? setDrawer(false) : setCollapsed((c) => !c))}
      onNavigate={inDrawer ? () => setDrawer(false) : undefined}
      onHelp={() => setHelp(true)}
      inDrawer={inDrawer}
      person={{ id: me?.id, name, role: topRole }}
    />
  );

  return (
    <StepUpProvider>
      <div className="adm" data-collapsed={ready && !narrow && collapsed} data-narrow={narrow}>
        <a className="adm-skip" href="#main">Skip to content</a>
        {ready && !narrow ? (
          <aside className="adm-side" aria-label="Sidebar">
            {sidebar(false)}
          </aside>
        ) : null}
        {ready && narrow ? (
          <Dialog.Root open={drawer} onOpenChange={setDrawer}>
            <Dialog.Portal>
              <Dialog.Overlay className="adm-scrim" />
              <Dialog.Content className="adm-drawer" aria-describedby={undefined}>
                <Dialog.Title className="wo-visually-hidden">Menu</Dialog.Title>
                {sidebar(true)}
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        ) : null}
        <div className="adm-main">
          <TopBar
            limited={!ready}
            narrow={narrow}
            onMenu={() => setDrawer(true)}
            onPalette={() => setPalette(true)}
            onHelp={() => setHelp(true)}
            pending={counts.registrations_awaiting_approval ?? 0}
            canSeePending={have.has("members.approve") && have.has("dashboard.view")}
            name={name}
            role={topRole}
          />
          <main className="adm-content" id="main" tabIndex={-1}>
            <ErrorBoundary resetKey={location.pathname}>
              {ready ? <Outlet /> : <MfaSetup onConfirmed={() => setSettingUp(true)} onDone={() => setSettingUp(false)} />}
            </ErrorBoundary>
          </main>
        </div>
        {ready ? <CommandPalette open={palette} onOpenChange={setPalette} permissions={have} /> : null}
        <Shortcuts open={help} onOpenChange={setHelp} />
      </div>
    </StepUpProvider>
  );
}
