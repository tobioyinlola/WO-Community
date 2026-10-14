import { useCallback, useId, useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { cx } from "../lib/cx";
import { useSideMenu } from "../lib/useSideMenu";

export interface NavLinkItem {
  label: string;
  href: string;
  /** Marks the page the member is on. */
  current?: boolean;
}

export interface LogoSources {
  /** Full logo for cream and white grounds. */
  fullOnLight: string;
  /** Full logo for forest and the dark theme. */
  fullOnDark: string;
  /** The mark alone, for narrow screens. */
  markOnLight: string;
  markOnDark: string;
}

export interface TopNavProps {
  logo: LogoSources;
  links: NavLinkItem[];
  /** Sign in, or the member's avatar menu. */
  tail?: ReactNode;
  /** `brand` is the forest band for marketing pages and always uses the on-dark logo. */
  variant?: "default" | "brand";
}

/** A logo that falls back to its name if the file is not there, so a missing asset never breaks a page. */
function Logo({ src, mark, className }: { src: string; mark?: boolean; className: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <span className={cx("wo-wordmark", className)}>{mark ? "WO" : "WO Community"}</span>;
  }
  return <img className={cx("wo-nav__logo", className)} src={src} alt="" onError={() => setFailed(true)} />;
}

/** The global header: 72px, logo left, up to five links, a trailing action. */
export function TopNav({ logo, links, tail, variant = "default" }: TopNavProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const closeMenu = useCallback(() => setOpen(false), []);
  useSideMenu(open, closeMenu);
  const brand = variant === "brand";

  return (
    <nav
      className={cx("wo-nav", brand && "wo-nav--brand wo-on-brand")}
      aria-label="Main"
    >
      <a href="/" aria-label="WO Community, home" style={{ display: "contents" }}>
        {brand ? (
          <>
            <Logo src={logo.fullOnDark} className="wo-nav__logo--full" />
            <Logo src={logo.markOnDark} mark className="wo-nav__logo--mark" />
          </>
        ) : (
          <>
            <Logo src={logo.fullOnLight} className="wo-nav__logo--full wo-logo-for-light" />
            <Logo src={logo.fullOnDark} className="wo-nav__logo--full wo-logo-for-dark" />
            <Logo src={logo.markOnLight} mark className="wo-nav__logo--mark wo-logo-for-light" />
            <Logo src={logo.markOnDark} mark className="wo-nav__logo--mark wo-logo-for-dark" />
          </>
        )}
      </a>
      <button
        type="button"
        className={cx("wo-btn wo-btn--sm wo-nav__menu", brand ? "wo-btn--on-brand" : "wo-btn--secondary")}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <X size={20} strokeWidth={1.5} aria-hidden="true" /> : <Menu size={20} strokeWidth={1.5} aria-hidden="true" />}
      </button>
      <div className="wo-nav__scrim" data-open={open} onClick={closeMenu} aria-hidden="true" />
      <div id={panelId} className="wo-nav__panel" data-open={open}>
        <ul className="wo-nav__links">
          {links.slice(0, 5).map((link) => (
            <li key={link.href}>
              <a
                className="wo-nav__link"
                href={link.href}
                aria-current={link.current ? "page" : undefined}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        {tail ? <div className="wo-nav__tail">{tail}</div> : null}
      </div>
    </nav>
  );
}
