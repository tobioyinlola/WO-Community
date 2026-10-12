import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { ROLE_LABELS, permissionsFor } from "../admin/permissions";
import { isTyping, useMediaQuery, usePref } from "../admin/shell/prefs";
import { Sidebar } from "../admin/shell/Sidebar";
import { visibleNav } from "../admin/shell/nav";
import { useAuth } from "../auth/AuthProvider";
import { PendingNotice } from "../pages/app/Pending";
import "../styles/admin.css";
import "../styles/member-shell.css";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { MemberTopBar } from "./shell/MemberTopBar";
import { MEMBER_NAV } from "./shell/memberNav";

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL ?? "support@withonyeka.com";
const SUPPORT_HREF = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent("WO Community support")}`;

/**
 * The signed-in frame, built the same way as the admin console: a floating sidebar that collapses
 * to a rail (a drawer on narrow screens), a floating top bar with search, and the page.
 */
export function AppLayout() {
  const { isPending, me } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const narrow = useMediaQuery("(max-width: 1023px)");
  const [collapsed, setCollapsed] = usePref("sidebar-collapsed", false);
  const [drawer, setDrawer] = useState(false);

  const roles = useMemo(() => me?.roles ?? [], [me?.roles]);
  const entries = useMemo(() => visibleNav(permissionsFor(roles), MEMBER_NAV), [roles]);

  const profile = useQuery({
    queryKey: ["me", "profile"],
    queryFn: () => unwrap(api.GET("/api/v1/me/profile")),
  });
  const name = profile.data?.full_name || me?.email || "Account";
  const role = ROLE_LABELS[roles.includes("mentor") ? "mentor" : "member"] ?? "Member";

  useEffect(() => setDrawer(false), [location.pathname, location.search]);

  useEffect(() => {
    if (isPending) return;
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "[" && !narrow) setCollapsed((c) => !c);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isPending, narrow, setCollapsed]);

  // location.key is "default" on the first page of a tab, where there is nothing to go back to.
  const goBack = () => (location.key === "default" ? navigate("/app") : navigate(-1));

  const sidebar = (inDrawer: boolean) => (
    <Sidebar
      entries={entries}
      counts={{}}
      collapsed={inDrawer ? false : collapsed}
      onToggle={() => (inDrawer ? setDrawer(false) : setCollapsed((c) => !c))}
      onNavigate={inDrawer ? () => setDrawer(false) : undefined}
      onHelp={() => undefined}
      inDrawer={inDrawer}
      person={{ id: me?.id, name, role: roles.includes("mentor") ? "mentor" : "member" }}
      home={{ to: "/app", label: "WO Community, home" }}
      navLabel="Main"
      help={{ label: "Contact support", href: SUPPORT_HREF }}
    />
  );

  return (
    <div className="adm" data-collapsed={!isPending && !narrow && collapsed} data-narrow={narrow || isPending}>
      <a className="adm-skip" href="#main">Skip to content</a>
      {!isPending && !narrow ? (
        <aside className="adm-side" aria-label="Sidebar">
          {sidebar(false)}
        </aside>
      ) : null}
      {!isPending && narrow ? (
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
        <MemberTopBar
          limited={isPending}
          narrow={narrow}
          onMenu={() => setDrawer(true)}
          name={name}
          photo={profile.data?.photo?.thumb}
          role={role}
        />
        <main className="adm-content" id="main" tabIndex={-1}>
          {isPending || location.pathname === "/app" ? null : (
            <button type="button" className="adm-back" onClick={goBack}>
              <ArrowLeft size={18} strokeWidth={1.5} aria-hidden="true" />
              Back
            </button>
          )}
          <ErrorBoundary resetKey={location.pathname}>{isPending ? <PendingNotice /> : <Outlet />}</ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
