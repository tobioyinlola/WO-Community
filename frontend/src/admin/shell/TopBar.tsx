import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, CircleHelp, Clock, Menu, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { Avatar, Logo } from "../../components";
import { formatTime } from "../../lib/format";
import { NotificationBell } from "../../shell/NotificationBell";
import { GlobalSearch } from "../../shell/GlobalSearch";
import type { QuickLink } from "../../shell/searchModel";
import { ROLE_LABELS } from "../permissions";

export function UserMenu({ name, role, onShortcuts }: { name: string; role: string; onShortcuts: () => void }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="adm-user" aria-label={`Account menu for ${name}`}>
          <Avatar name={name} id={me?.id} size="sm" />
          <span className="adm-user__text">
            <span className="adm-user__name">{name}</span>
            <span className="adm-user__role">{ROLE_LABELS[role] ?? role}</span>
          </span>
          <ChevronDown size={16} strokeWidth={1.5} aria-hidden="true" className="adm-user__chevron" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={10} className="adm-menu">
          <div className="adm-menu__who">
            <p className="adm-menu__name">{name}</p>
            <p className="adm-menu__email">{me?.email}</p>
          </div>
          <DropdownMenu.Separator className="adm-menu__sep" />
          <DropdownMenu.Item asChild>
            <Link to="/admin/settings?section=profile" className="adm-menu__item">Your profile</Link>
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="adm-menu__sep" />
          <DropdownMenu.Item className="adm-menu__item" onSelect={onShortcuts}>
            Keyboard shortcuts
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="adm-menu__sep" />
          <DropdownMenu.Item
            className="adm-menu__item"
            onSelect={() => {
              // Leave first so ending the session cannot race the route guard.
              navigate("/login", { replace: true });
              void logout();
            }}
          >
            Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function LocalTime() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(tick);
  }, []);
  return (
    <span className="adm-chip adm-chip--quiet">
      <Clock size={16} strokeWidth={1.5} aria-hidden="true" />
      <span className="adm-chip__label">Local time</span>
      <time dateTime={now.toISOString()}>{formatTime(now)}</time>
    </span>
  );
}

interface TopBarProps {
  /** Before two step sign in is done only the account menu is offered. */
  limited?: boolean;
  narrow: boolean;
  onMenu: () => void;
  /** Pages and quick actions this role may use, offered by the search field. */
  links: QuickLink[];
  onHelp: () => void;
  pending: number;
  canSeePending: boolean;
  name: string;
  role: string;
}

export function TopBar({ limited = false, narrow, onMenu, links, onHelp, pending, canSeePending, name, role }: TopBarProps) {
  const { me } = useAuth();
  // Admin accounts are not always members, and the notification centre is a member feature.
  const isMember = (me?.roles ?? []).some((r) => r === "member" || r === "mentor");
  if (limited) {
    return (
      <header className="adm-top">
        <div className="adm-top__tail">
          <UserMenu name={name} role={role} onShortcuts={onHelp} />
        </div>
      </header>
    );
  }
  return (
    <header className="adm-top">
      {narrow ? (
        <button type="button" className="adm-iconbtn" onClick={onMenu} aria-label="Open menu">
          <Menu size={22} strokeWidth={1.5} aria-hidden="true" />
        </button>
      ) : null}
      {narrow ? (
        <Link to="/admin" className="adm-top__logo" aria-label="WO Community, home">
          <Logo kind="mark" height={30} />
        </Link>
      ) : null}
      <GlobalSearch scope="admin" links={links} resultsPath="/admin/search" placeholder="Search members, courses, jobs, pages" />
      <div className="adm-top__tail">
        {canSeePending ? (
          <Link to="/admin/approvals" className="adm-chip">
            <UserCheck size={16} strokeWidth={1.5} aria-hidden="true" />
            <span className="adm-chip__label">Pending approvals</span>
            <strong className="adm-chip__count">{pending}</strong>
          </Link>
        ) : null}
        <LocalTime />
        <button type="button" className="adm-iconbtn adm-iconbtn--ring adm-top__help" onClick={onHelp} aria-label="Help and shortcuts">
          <CircleHelp size={20} strokeWidth={1.5} aria-hidden="true" />
        </button>
        <NotificationBell enabled={isMember} />
        <UserMenu name={name} role={role} onShortcuts={onHelp} />
      </div>
    </header>
  );
}
