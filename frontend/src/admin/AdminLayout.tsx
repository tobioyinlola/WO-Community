import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Briefcase,
  CalendarDays,
  GraduationCap,
  Newspaper,
  Flag,
  LayoutDashboard,
  ListChecks,
  Mail,
  Menu,
  ShieldCheck,
  Trophy,
  UserCheck,
  UserPlus,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { getAccessToken, onTokenChange } from "../api/session";
import { useAuth } from "../auth/AuthProvider";
import { Logo } from "../components";
import { UserMenu } from "../layouts/AppLayout";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { mfaAgeSeconds } from "./claims";
import MfaSetup from "./MfaSetup";
import { isAdmin, permissionsFor } from "./permissions";
import { StepUpProvider } from "./StepUp";

interface Item {
  to: string;
  label: string;
  icon: LucideIcon;
  needs: string;
  end?: boolean;
  badge?: "registrations_awaiting_approval" | "open_reports" | "jobs_awaiting_review" | "wins_awaiting_review";
}

const GROUPS: Array<{ title: string; items: Item[] }> = [
  { title: "", items: [{ to: "/admin", label: "Overview", icon: LayoutDashboard, needs: "dashboard.view", end: true }] },
  {
    title: "People",
    items: [
      { to: "/admin/members", label: "Members", icon: Users, needs: "members.view", badge: "registrations_awaiting_approval" },
      { to: "/admin/invitations", label: "Invitations", icon: UserPlus, needs: "invitations.manage" },
      { to: "/admin/mentors", label: "Mentor applications", icon: UserCheck, needs: "mentors.decide" },
    ],
  },
  {
    title: "Moderation",
    items: [
      { to: "/admin/reports", label: "Reports", icon: Flag, needs: "reports.handle", badge: "open_reports" },
      { to: "/admin/jobs", label: "Jobs", icon: Briefcase, needs: "jobs.moderate", badge: "jobs_awaiting_review" },
      { to: "/admin/wins", label: "Wins", icon: Trophy, needs: "editorial.manage", badge: "wins_awaiting_review" },
    ],
  },
  {
    title: "Content",
    items: [
      { to: "/admin/news", label: "News", icon: Newspaper, needs: "editorial.manage" },
      { to: "/admin/events", label: "Events", icon: CalendarDays, needs: "events.manage" },
      { to: "/admin/courses", label: "Courses", icon: GraduationCap, needs: "courses.manage" },
      { to: "/admin/email", label: "Email", icon: Mail, needs: "campaigns.send" },
    ],
  },
  { title: "Settings", items: [{ to: "/admin/lists", label: "Lists", icon: ListChecks, needs: "reference.manage" }] },
];

/** The first section a person may open, used when they land on the console. */
export function firstAllowed(roles: readonly string[]): string {
  const have = permissionsFor(roles);
  for (const group of GROUPS) for (const item of group.items) if (have.has(item.needs)) return item.to;
  return "/admin/security";
}

/** The console frame. Admin accounts must have passed a second step before anything opens. */
export function AdminLayout() {
  const { me } = useAuth();
  const location = useLocation();
  const [drawer, setDrawer] = useState(false);
  // Re-read the session whenever the token changes (after enrolling or a step up check).
  useSyncExternalStore(onTokenChange as (cb: () => void) => () => void, getAccessToken);
  const roles = me?.roles ?? [];
  const have = permissionsFor(roles);
  const counts = useQuery({
    queryKey: ["admin", "queues"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/queues")),
    enabled: isAdmin(roles) && mfaAgeSeconds() !== null && have.has("dashboard.view"),
    refetchInterval: 60_000,
  });
  const [settingUp, setSettingUp] = useState(false);

  useEffect(() => setDrawer(false), [location.pathname]);

  if (!isAdmin(roles)) return <Navigate to="/app" replace />;
  const verified = mfaAgeSeconds() !== null;

  return (
    <StepUpProvider>
      <div className="app-shell">
        <aside className="app-side" data-open={drawer} aria-label="Console sections">
          <Link to="/admin" className="app-side__logo" aria-label="WO Community console, home">
            <Logo height={40} />
          </Link>
          <p className="app-nav__group" style={{ marginTop: 0 }}>Admin console</p>
          {verified && !settingUp ? (
            <nav aria-label="Admin">
              {GROUPS.map((group) => {
                const items = group.items.filter((i) => have.has(i.needs));
                if (items.length === 0) return null;
                return (
                  <div key={group.title || "top"}>
                    {group.title ? <p className="app-nav__group">{group.title}</p> : null}
                    <ul className="app-nav">
                      {items.map((item) => {
                        const n = item.badge ? counts.data?.[item.badge] ?? 0 : 0;
                        return (
                          <li key={item.to}>
                            <NavLink to={item.to} end={item.end} className="app-nav__link">
                              <item.icon size={20} strokeWidth={1.5} aria-hidden="true" />
                              {item.label}
                              {n > 0 ? <span className="app-nav__badge" aria-label={`${n} waiting`}>{n}</span> : null}
                            </NavLink>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
              <p className="app-nav__group">Account</p>
              <ul className="app-nav">
                <li>
                  <NavLink to="/admin/security" className="app-nav__link"><ShieldCheck size={20} strokeWidth={1.5} aria-hidden="true" />Security</NavLink>
                </li>
                <li>
                  <Link to="/app" className="app-nav__link"><ArrowLeft size={20} strokeWidth={1.5} aria-hidden="true" />Back to the community</Link>
                </li>
              </ul>
            </nav>
          ) : null}
        </aside>
        <div className="app-scrim" data-open={drawer} onClick={() => setDrawer(false)} aria-hidden="true" />
        <header className="app-head">
          <button type="button" className="app-iconbtn app-head__menu" aria-label={drawer ? "Close menu" : "Open menu"} aria-expanded={drawer} onClick={() => setDrawer((v) => !v)}>
            {drawer ? <X size={22} strokeWidth={1.5} /> : <Menu size={22} strokeWidth={1.5} />}
          </button>
          <div className="app-head__search" aria-hidden="true" />
          <div className="app-head__tail"><UserMenu /></div>
        </header>
        <main className="app-main" id="main">
          <div className="app-main__inner">
            <ErrorBoundary resetKey={location.pathname}>
              {verified && !settingUp ? <Outlet /> : <MfaSetup onConfirmed={() => setSettingUp(true)} onDone={() => setSettingUp(false)} />}
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </StepUpProvider>
  );
}
