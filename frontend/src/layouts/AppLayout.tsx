import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  Briefcase,
  CalendarDays,
  GraduationCap,
  Home,
  LogOut,
  Megaphone,
  Menu,
  MessageSquare,
  Rocket,
  Search,
  Settings,
  UserCircle,
  UserCheck,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Avatar, Logo } from "../components";
import { PendingNotice } from "../pages/app/Pending";
import { ErrorBoundary } from "../ui/ErrorBoundary";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const MAIN: NavItem[] = [
  { to: "/app", label: "Home", icon: Home, end: true },
  { to: "/app/feed", label: "Feed", icon: MessageSquare },
  { to: "/app/directory", label: "Directory", icon: Users },
  { to: "/app/jobs", label: "Jobs", icon: Briefcase },
  { to: "/app/events", label: "Events", icon: CalendarDays },
  { to: "/app/learn", label: "Learn", icon: GraduationCap },
  { to: "/app/mentors", label: "Mentors", icon: UserCheck },
  { to: "/app/news", label: "News", icon: Megaphone },
];
const BUILD: NavItem[] = [{ to: "/app/launch", label: "Launch toolkit", icon: Rocket }];

function NavList({ items, unread }: { items: NavItem[]; unread: number }) {
  return (
    <ul className="app-nav">
      {items.map((item) => (
        <li key={item.to}>
          <NavLink to={item.to} end={item.end} className="app-nav__link">
            <item.icon size={20} strokeWidth={1.5} aria-hidden="true" />
            {item.label}
            {item.to === "/app/notifications" && unread > 0 ? (
              <span className="app-nav__badge">{unread}</span>
            ) : null}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const profile = useQuery({
    queryKey: ["me", "profile"],
    queryFn: () => unwrap(api.GET("/api/v1/me/profile")),
  });
  const name = profile.data?.full_name || me?.email || "Account";

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setOpen(false);
      } else if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div className="app-menu" ref={ref}>
      <button
        type="button"
        className="app-iconbtn"
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Avatar name={name} id={me?.id} src={profile.data?.photo?.thumb} size="sm" />
      </button>
      {open ? (
        <div className="app-menu__panel" role="menu">
          <div className="app-menu__who">
            <p className="body-strong" style={{ margin: 0 }}>
              {name}
            </p>
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              {me?.email}
            </p>
          </div>
          <Link className="app-menu__item" role="menuitem" to="/app/me" onClick={() => setOpen(false)}>
            <UserCircle size={20} strokeWidth={1.5} aria-hidden="true" />
            Your profile
          </Link>
          <Link
            className="app-menu__item"
            role="menuitem"
            to="/app/settings"
            onClick={() => setOpen(false)}
          >
            <Settings size={20} strokeWidth={1.5} aria-hidden="true" />
            Settings
          </Link>
          <button
            type="button"
            className="app-menu__item"
            role="menuitem"
            onClick={async () => {
              setOpen(false);
              // Leave first: once the session ends the route guard would send the member to the sign in page.
              navigate("/", { replace: true });
              await logout();
            }}
          >
            <LogOut size={20} strokeWidth={1.5} aria-hidden="true" />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** The signed-in frame: sidebar, header with search and notifications, and the page. */
export function AppLayout() {
  const { isPending } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [term, setTerm] = useState("");

  const notifications = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => unwrap(api.GET("/api/v1/notifications", { params: { query: { limit: 1 } } })),
    enabled: !isPending,
    refetchInterval: 60_000,
  });
  const unread = notifications.data?.unread_count ?? 0;

  useEffect(() => setDrawer(false), [location.pathname]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = term.trim();
    if (q) navigate(`/app/directory?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="app-shell">
      <aside className="app-side" data-open={drawer} aria-label="Sections">
        <Link to="/app" className="app-side__logo" aria-label="WO Community, home">
          <Logo height={40} />
        </Link>
        {isPending ? null : (
          <nav aria-label="Main">
            <NavList items={MAIN} unread={unread} />
            <p className="app-nav__group">Build</p>
            <NavList items={BUILD} unread={unread} />
          </nav>
        )}
      </aside>
      <div className="app-scrim" data-open={drawer} onClick={() => setDrawer(false)} aria-hidden="true" />
      <header className="app-head">
        <button
          type="button"
          className="app-iconbtn app-head__menu"
          aria-label={drawer ? "Close menu" : "Open menu"}
          aria-expanded={drawer}
          onClick={() => setDrawer((value) => !value)}
        >
          {drawer ? <X size={22} strokeWidth={1.5} /> : <Menu size={22} strokeWidth={1.5} />}
        </button>
        {isPending ? null : (
          <form className="app-head__search" role="search" onSubmit={submit}>
            <label className="wo-visually-hidden" htmlFor="app-search">
              Search the community
            </label>
            <div style={{ position: "relative" }}>
              <Search
                size={18}
                strokeWidth={1.5}
                aria-hidden="true"
                style={{ position: "absolute", left: 14, top: 14, color: "var(--text-tertiary)" }}
              />
              <input
                id="app-search"
                className="wo-input"
                style={{ height: "var(--control-md)", paddingLeft: 40 }}
                placeholder="Search members, startups, jobs"
                value={term}
                onChange={(event) => setTerm(event.target.value)}
              />
            </div>
          </form>
        )}
        <div className="app-head__tail">
          {isPending ? null : (
            <Link
              to="/app/notifications"
              className="app-iconbtn"
              aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
            >
              <Bell size={22} strokeWidth={1.5} aria-hidden="true" />
              {unread > 0 ? <span className="app-iconbtn__dot">{unread > 9 ? "9+" : unread}</span> : null}
            </Link>
          )}
          <UserMenu />
        </div>
      </header>
      <main className="app-main" id="main">
        <div className="app-main__inner">
          <ErrorBoundary resetKey={location.pathname}>{isPending ? <PendingNotice /> : <Outlet />}</ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
