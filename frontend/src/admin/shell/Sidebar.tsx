import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ChevronDown, CircleHelp, LifeBuoy, PanelLeftClose, PanelLeftOpen, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Avatar, Logo } from "../../components";
import { FULL_LOGO_MIN_HEIGHT } from "../../components/Logo";
import { ROLE_LABELS } from "../permissions";
import { isCurrent, isGroup, type NavEntry, type NavGroup, type NavLeaf, type QueueKey } from "./nav";
import { usePref } from "./prefs";

export type Counts = Partial<Record<QueueKey, number>>;

interface SidebarProps {
  entries: NavEntry[];
  counts: Counts;
  collapsed: boolean;
  onToggle: () => void;
  /** Called after a link is followed, so a drawer can close. */
  onNavigate?: () => void;
  onHelp: () => void;
  /** Inside the mobile drawer the toggle closes the drawer instead of collapsing the rail. */
  inDrawer?: boolean;
  person: { id?: string; name: string; role: string };
  /** Where the logo goes, and what it is called. The console is the default. */
  home?: { to: string; label: string };
  /** The accessible name of the navigation landmark. */
  navLabel?: string;
  /** When set, the help entry at the foot is a link (for example to email support) instead of the shortcuts button. */
  help?: { label: string; href?: string; onClick?: () => void };
}

function Badge({ leaf, counts }: { leaf: NavLeaf; counts: Counts }) {
  const n = leaf.badge ? (counts[leaf.badge] ?? 0) : 0;
  if (n <= 0) return null;
  return (
    <span className="adm-nav__count" aria-label={`${n} waiting`}>
      {n > 99 ? "99+" : n}
    </span>
  );
}

function Leaf({
  leaf,
  icon: Icon,
  counts,
  collapsed,
  nested = false,
  onNavigate,
}: {
  leaf: NavLeaf;
  icon?: LucideIcon;
  counts: Counts;
  collapsed: boolean;
  nested?: boolean;
  onNavigate?: () => void;
}) {
  const location = useLocation();
  const current = isCurrent(leaf.to, location.pathname, location.search, leaf.end);
  const rail = collapsed && !nested;
  const link = (
    <Link
      to={leaf.to}
      className="adm-nav__link"
      data-current={current}
      data-rail={rail}
      aria-current={current ? "page" : undefined}
      aria-label={rail ? leaf.label : undefined}
      onClick={onNavigate}
    >
      {Icon ? <Icon size={20} strokeWidth={1.5} aria-hidden="true" /> : <span className="adm-nav__dot" aria-hidden="true" />}
      {rail ? null : <span className="adm-nav__label">{leaf.label}</span>}
      {rail ? null : leaf.soon ? <span className="adm-nav__soon">Soon</span> : null}
      {rail ? null : <Badge leaf={leaf} counts={counts} />}
      {rail && leaf.badge && (counts[leaf.badge] ?? 0) > 0 ? <span className="adm-nav__pip" aria-hidden="true" /> : null}
    </Link>
  );
  if (!rail) return <li>{link}</li>;
  return (
    <li>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{link}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content side="right" sideOffset={12} className="adm-tip">
            {leaf.label}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </li>
  );
}

/** In the collapsed rail a group is one icon; its pages appear in a flyout beside it. */
function RailGroup({ group, counts, active }: { group: NavGroup; counts: Counts; active: boolean }) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number>();
  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    timer.current = window.setTimeout(() => setOpen(false), 150);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const waiting = group.children.reduce((sum, c) => sum + (c.badge ? (counts[c.badge] ?? 0) : 0), 0);
  const Icon = group.icon;
  return (
    <li>
      <DropdownMenu.Root open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            className="adm-nav__link"
            data-rail="true"
            data-current={active}
            aria-label={group.label}
            onPointerEnter={show}
            onPointerLeave={hide}
            onFocus={show}
          >
            <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
            {waiting > 0 ? <span className="adm-nav__pip" aria-hidden="true" /> : null}
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content side="right" align="start" sideOffset={12} className="adm-flyout" onPointerEnter={show} onPointerLeave={hide}>
            <DropdownMenu.Label className="adm-flyout__title">{group.label}</DropdownMenu.Label>
            {group.children.map((child) => (
              <DropdownMenu.Item key={child.id} asChild>
                <Link to={child.to} className="adm-flyout__item">
                  <span>{child.label}</span>
                  {child.soon ? <span className="adm-nav__soon">Soon</span> : <Badge leaf={child} counts={counts} />}
                </Link>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </li>
  );
}

function Group({
  group,
  counts,
  open,
  onToggle,
  onNavigate,
}: {
  group: NavGroup;
  counts: Counts;
  open: boolean;
  onToggle: () => void;
  onNavigate?: () => void;
}) {
  const Icon = group.icon;
  const panel = `adm-group-${group.id}`;
  const waiting = group.children.reduce((sum, c) => sum + (c.badge ? (counts[c.badge] ?? 0) : 0), 0);
  return (
    <li>
      <button type="button" className="adm-nav__link adm-nav__link--group" aria-expanded={open} aria-controls={panel} onClick={onToggle}>
        <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
        <span className="adm-nav__label">{group.label}</span>
        {!open && waiting > 0 ? <span className="adm-nav__count" aria-label={`${waiting} waiting`}>{waiting}</span> : null}
        <ChevronDown size={18} strokeWidth={1.5} aria-hidden="true" className="adm-nav__chevron" data-open={open} />
      </button>
      <div id={panel} className="adm-nav__sub" data-open={open} hidden={!open}>
        <ul className="adm-nav__list">
          {group.children.map((child) => (
            <Leaf key={child.id} leaf={child} counts={counts} collapsed={false} nested onNavigate={onNavigate} />
          ))}
        </ul>
      </div>
    </li>
  );
}

export function Sidebar({ entries, counts, collapsed, onToggle, onNavigate, onHelp, inDrawer = false, person, home = { to: "/admin", label: "WO Community admin, dashboard" }, navLabel = "Admin sections", help }: SidebarProps) {
  const location = useLocation();
  const [openGroups, setOpenGroups] = usePref<string[]>("open-groups", []);

  const activeGroup = entries.find(
    (e): e is NavGroup => isGroup(e) && e.children.some((c) => isCurrent(c.to, location.pathname, location.search, c.end)),
  )?.id;

  // Open the group that holds the page being shown, so the active item is never hidden.
  useEffect(() => {
    if (activeGroup) setOpenGroups((current) => (current.includes(activeGroup) ? current : [...current, activeGroup]));
  }, [activeGroup, setOpenGroups]);

  const toggleGroup = (id: string) => setOpenGroups((current) => (current.includes(id) ? current.filter((g) => g !== id) : [...current, id]));

  return (
    <Tooltip.Provider delayDuration={150}>
      <div className="adm-side__inner" data-collapsed={collapsed}>
        <div className="adm-side__head">
          <Link to={home.to} className="adm-side__logo" aria-label={home.label} onClick={onNavigate}>
            <Logo kind={collapsed ? "mark" : "full"} height={collapsed ? 32 : FULL_LOGO_MIN_HEIGHT} />
          </Link>
          <button
            type="button"
            className="adm-iconbtn adm-side__toggle"
            onClick={onToggle}
            aria-label={inDrawer ? "Close menu" : collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={inDrawer ? undefined : !collapsed}
            aria-keyshortcuts={inDrawer ? undefined : "["}
            title={inDrawer ? "Close menu" : collapsed ? "Expand sidebar ([)" : "Collapse sidebar ([)"}
          >
            {inDrawer ? <X size={20} strokeWidth={1.5} aria-hidden="true" /> : collapsed ? <PanelLeftOpen size={20} strokeWidth={1.5} aria-hidden="true" /> : <PanelLeftClose size={20} strokeWidth={1.5} aria-hidden="true" />}
          </button>
        </div>

        <nav className="adm-side__nav" aria-label={navLabel}>
          <ul className="adm-nav__list">
            {entries.map((entry) => {
              if (!isGroup(entry)) return <Leaf key={entry.id} leaf={entry} icon={entry.icon} counts={counts} collapsed={collapsed} onNavigate={onNavigate} />;
              if (collapsed) return <RailGroup key={entry.id} group={entry} counts={counts} active={activeGroup === entry.id} />;
              return (
                <Group key={entry.id} group={entry} counts={counts} open={openGroups.includes(entry.id)} onToggle={() => toggleGroup(entry.id)} onNavigate={onNavigate} />
              );
            })}
          </ul>
        </nav>

        <div className="adm-side__foot">
          <div className="adm-person">
            <Avatar name={person.name} id={person.id} size="sm" />
            {collapsed ? null : (
              <div className="adm-person__text">
                <span className="adm-person__name">{person.name}</span>
                <span className="adm-person__role">{ROLE_LABELS[person.role] ?? person.role}</span>
              </div>
            )}
          </div>
          {help ? (
            <button
              type="button"
              className="adm-nav__link adm-nav__link--help"
              data-rail={collapsed}
              onClick={help.onClick}
              aria-label={collapsed ? help.label : undefined}
              title={collapsed ? help.label : undefined}
            >
              <LifeBuoy size={20} strokeWidth={1.5} aria-hidden="true" />
              {collapsed ? null : <span className="adm-nav__label">{help.label}</span>}
            </button>
          ) : (
            <button type="button" className="adm-nav__link adm-nav__link--help" data-rail={collapsed} onClick={onHelp} aria-label={collapsed ? "Help and shortcuts" : undefined}>
              <CircleHelp size={20} strokeWidth={1.5} aria-hidden="true" />
              {collapsed ? null : <span className="adm-nav__label">Help and shortcuts</span>}
            </button>
          )}
        </div>
      </div>
    </Tooltip.Provider>
  );
}
