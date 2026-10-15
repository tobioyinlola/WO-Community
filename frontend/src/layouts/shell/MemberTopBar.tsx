import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Menu } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useSupport } from "../../support/SupportProvider";
import { isAdmin } from "../../admin/permissions";
import { useAuth } from "../../auth/AuthProvider";
import { Avatar, Logo } from "../../components";
import { GlobalSearch } from "../../shell/GlobalSearch";
import { MEMBER_LINKS } from "../../shell/searchModel";
import { NotificationBell } from "../../shell/NotificationBell";

function AccountMenu({ name, photo, role }: { name: string; photo?: string | null; role: string }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const support = useSupport();
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
          <DropdownMenu.Item asChild>
            <Link to="/app/support" className="adm-menu__item">My support requests</Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item className="adm-menu__item" onSelect={() => support.open()}>
            Contact support
          </DropdownMenu.Item>
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
  name: string;
  photo?: string | null;
  role: string;
}

export function MemberTopBar({ limited, narrow, onMenu, name, photo, role }: MemberTopBarProps) {
  return (
    <header className="adm-top">
      {narrow && !limited ? (
        <button type="button" className="adm-iconbtn" onClick={onMenu} aria-label="Open menu">
          <Menu size={22} strokeWidth={1.5} aria-hidden="true" />
        </button>
      ) : null}
      {narrow ? (
        <Link to="/app" className="adm-top__logo" aria-label="WO Community, home">
          <Logo kind="mark" height={30} />
        </Link>
      ) : null}
      {limited ? null : <GlobalSearch scope="member" links={MEMBER_LINKS} resultsPath="/app/search" placeholder="Search members, startups, courses" />}
      <div className="adm-top__tail">
        {limited ? null : <NotificationBell />}
        <AccountMenu name={name} photo={photo} role={role} />
      </div>
    </header>
  );
}
