import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bell, ChevronDown, Menu, Monitor, Moon, Search, Sun } from "lucide-react";
import { forwardRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { isAdmin } from "../../admin/permissions";
import { useAuth } from "../../auth/AuthProvider";
import { Avatar } from "../../components";
import { useTheme, type ThemeChoice } from "../../theme/ThemeProvider";

const THEMES: Array<{ value: ThemeChoice; label: string; icon: typeof Sun }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "Match my device", icon: Monitor },
];

function AccountMenu({ name, photo, role }: { name: string; photo?: string | null; role: string }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const { choice, setChoice } = useTheme();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="adm-user" aria-label="Account menu">
          <Avatar name={name} id={me?.id} src={photo ?? undefined} size="sm" />
          <span className="adm-user__text">
            <span className="adm-user__name">{name}</span>
            <span className="adm-user__role">{role}</span>
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
          {isAdmin(me?.roles ?? []) ? (
            <DropdownMenu.Item asChild>
              <Link to="/admin" className="adm-menu__item">Admin console</Link>
            </DropdownMenu.Item>
          ) : null}
          <DropdownMenu.Item asChild>
            <Link to="/app/me" className="adm-menu__item">Your profile</Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <Link to="/app/settings" className="adm-menu__item">Settings</Link>
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
          <DropdownMenu.Item
            className="adm-menu__item"
            onSelect={() => {
              // Go to the sign in page first, so ending the session cannot race the route guard.
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

interface MemberTopBarProps {
  /** While the account waits for approval only the account menu is offered. */
  limited: boolean;
  narrow: boolean;
  onMenu: () => void;
  unread: number;
  name: string;
  photo?: string | null;
  role: string;
}

/** The search box is a real form field, so it can be typed in without opening anything first. */
export const MemberTopBar = forwardRef<HTMLInputElement, MemberTopBarProps>(function MemberTopBar(
  { limited, narrow, onMenu, unread, name, photo, role },
  searchRef,
) {
  const navigate = useNavigate();
  const [term, setTerm] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = term.trim();
    if (q) navigate(`/app/directory?q=${encodeURIComponent(q)}`);
  };
  return (
    <header className="adm-top">
      {narrow && !limited ? (
        <button type="button" className="adm-iconbtn" onClick={onMenu} aria-label="Open menu">
          <Menu size={22} strokeWidth={1.5} aria-hidden="true" />
        </button>
      ) : null}
      {limited ? null : (
        <form className="adm-search adm-search--field" role="search" onSubmit={submit}>
          <label className="wo-visually-hidden" htmlFor="app-search">Search the community</label>
          <Search size={18} strokeWidth={1.5} aria-hidden="true" />
          <input
            id="app-search"
            ref={searchRef}
            type="search"
            placeholder="Search members, startups, jobs"
            value={term}
            aria-keyshortcuts="/"
            onChange={(event) => setTerm(event.target.value)}
          />
          <kbd className="adm-kbd" aria-hidden="true">/</kbd>
        </form>
      )}
      <div className="adm-top__tail">
        {limited ? null : (
          <Link to="/app/notifications" className="adm-iconbtn adm-iconbtn--ring" aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}>
            <Bell size={20} strokeWidth={1.5} aria-hidden="true" />
            {unread > 0 ? <span className="adm-dot" aria-hidden="true" /> : null}
          </Link>
        )}
        <AccountMenu name={name} photo={photo} role={role} />
      </div>
    </header>
  );
});
