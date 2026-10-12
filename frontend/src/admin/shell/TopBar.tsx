import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import { Bell, ChevronDown, CircleHelp, Clock, Menu, Monitor, Moon, Search, Sun, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Avatar } from "../../components";
import { formatTime } from "../../lib/format";
import { useTheme, type ThemeChoice } from "../../theme/ThemeProvider";
import { ROLE_LABELS } from "../permissions";

const THEMES: Array<{ value: ThemeChoice; label: string; icon: typeof Sun }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "Match my device", icon: Monitor },
];

export function UserMenu({ name, role, onShortcuts }: { name: string; role: string; onShortcuts: () => void }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const { choice, setChoice } = useTheme();
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
          <DropdownMenu.Label className="adm-menu__label">Theme</DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={choice} onValueChange={(v) => setChoice(v as ThemeChoice)}>
            {THEMES.map(({ value, label, icon: Icon }) => (
              <DropdownMenu.RadioItem key={value} value={value} className="adm-menu__item adm-menu__radio">
                <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                <span>{label}</span>
                <DropdownMenu.ItemIndicator className="adm-menu__tick" aria-hidden="true">{"✓"}</DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          <DropdownMenu.Separator className="adm-menu__sep" />
          <DropdownMenu.Item className="adm-menu__item" onSelect={onShortcuts}>
            Keyboard shortcuts
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <Link to="/app" className="adm-menu__item">Back to the community</Link>
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
  onPalette: () => void;
  onHelp: () => void;
  pending: number;
  canSeePending: boolean;
  name: string;
  role: string;
}

export function TopBar({ limited = false, narrow, onMenu, onPalette, onHelp, pending, canSeePending, name, role }: TopBarProps) {
  const { me } = useAuth();
  // Admin accounts are not always members, and the notification centre is a member feature.
  const isMember = (me?.roles ?? []).some((r) => r === "member" || r === "mentor");
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    enabled: isMember,
    queryFn: () => unwrap(api.GET("/api/v1/notifications", { params: { query: { limit: 1 } } })),
    refetchInterval: 60_000,
  });
  const count = unread.data?.unread_count ?? 0;
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
      <button type="button" className="adm-search" onClick={onPalette} aria-label="Search and jump to a page" aria-keyshortcuts="Control+K Meta+K">
        <Search size={18} strokeWidth={1.5} aria-hidden="true" />
        <span className="adm-search__hint">Search members, ventures, jobs, pages…</span>
        <kbd className="adm-kbd" aria-hidden="true">Ctrl K</kbd>
      </button>
      <div className="adm-top__tail">
        {canSeePending ? (
          <Link to="/admin/approvals" className="adm-chip">
            <UserCheck size={16} strokeWidth={1.5} aria-hidden="true" />
            <span className="adm-chip__label">Pending approvals</span>
            <strong className="adm-chip__count">{pending}</strong>
          </Link>
        ) : null}
        <LocalTime />
        <button type="button" className="adm-iconbtn adm-iconbtn--ring" onClick={onHelp} aria-label="Help and shortcuts">
          <CircleHelp size={20} strokeWidth={1.5} aria-hidden="true" />
        </button>
        <Link to="/app/notifications" className="adm-iconbtn adm-iconbtn--ring" aria-label={count > 0 ? `Notifications, ${count} unread` : "Notifications"}>
          <Bell size={20} strokeWidth={1.5} aria-hidden="true" />
          {count > 0 ? <span className="adm-dot" aria-hidden="true" /> : null}
        </Link>
        <UserMenu name={name} role={role} onShortcuts={onHelp} />
      </div>
    </header>
  );
}
