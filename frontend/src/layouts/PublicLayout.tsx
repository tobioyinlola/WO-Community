import { Link, NavLink, Outlet } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { Instagram, Linkedin, Menu, Twitter, X, Youtube, type LucideIcon } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { Logo } from "../components";
import { useSideMenu } from "../lib/useSideMenu";
import { SOCIAL_LINKS } from "../pages/public/landingContent";
import { ArrowCircle } from "../ui/ArrowCircle";

const SOCIAL: Record<(typeof SOCIAL_LINKS)[number]["kind"], { label: string; icon: LucideIcon }> = {
  linkedin: { label: "LinkedIn", icon: Linkedin },
  x: { label: "X", icon: Twitter },
  instagram: { label: "Instagram", icon: Instagram },
  youtube: { label: "YouTube", icon: Youtube },
};

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/explore", label: "Explore" },
  { to: "/news", label: "News" },
];

/** The public site: a forest band header, the page, and a forest footer. */
export function PublicLayout() {
  const { status } = useAuth();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const signedIn = status === "authenticated";
  const closeMenu = useCallback(() => setOpen(false), []);
  useSideMenu(open, closeMenu);

  // The floating header turns into a blurred, slightly see-through bar once the page has moved.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <a href="#main" className="wo-visually-hidden">
        Skip to content
      </a>
      <nav className="wo-nav wo-nav--brand wo-on-brand site-head" aria-label="Main" data-scrolled={scrolled}>
        <Link to="/" aria-label="WO Community, home">
          <Logo on="dark" kind="mark" height={40} />
        </Link>
        <button
          type="button"
          className="wo-btn wo-btn--sm wo-btn--on-brand wo-nav__menu"
          aria-expanded={open}
          aria-controls="site-panel"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X size={20} strokeWidth={1.5} /> : <Menu size={20} strokeWidth={1.5} />}
        </button>
        <div className="wo-nav__scrim" data-open={open} onClick={closeMenu} aria-hidden="true" />
        <div id="site-panel" className="wo-nav__panel" data-open={open}>
          <ul className="wo-nav__links">
            {LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.end}
                  className="wo-nav__link"
                  onClick={closeMenu}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="wo-nav__tail">
            {signedIn ? (
              <Link className="wo-btn wo-btn--accent wo-btn--sm" to="/app" onClick={closeMenu}>
                Open the app
                <ArrowCircle />
              </Link>
            ) : (
              <>
                <Link className="wo-btn wo-btn--on-brand wo-btn--sm" to="/login" onClick={closeMenu}>
                  Sign in
                </Link>
                <Link className="wo-btn wo-btn--accent wo-btn--sm" to="/register" onClick={closeMenu}>
                  Request access
                  <ArrowCircle />
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>
      <main id="main">
        <Outlet />
      </main>
      <footer className="site-footer wo-on-brand">
        <div className="wo-container">
          <div className="site-footer__card wo-on-brand">
          <div className="site-footer__grid">
            <div>
              <Logo on="dark" height={120} />
              <p className="body" style={{ maxWidth: "36ch", marginTop: "var(--space-4)", color: "var(--text-on-brand-muted)" }}>
                Africa&rsquo;s most intentional founder, operator and investor ecosystem.
              </p>
              {SOCIAL_LINKS.length > 0 ? (
                <ul className="site-footer__social" aria-label="WO Community on social media">
                  {SOCIAL_LINKS.map((link) => {
                    const { label, icon: Icon } = SOCIAL[link.kind];
                    return (
                      <li key={link.kind}>
                        <a className="site-roundbtn" href={link.href} target="_blank" rel="noopener noreferrer" aria-label={`${label} (opens in a new tab)`}>
                          <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                        </a>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>
            <div>
              <span className="wo-eyebrow">Community</span>
              <ul className="site-footer__list">
                <li><Link to="/explore">Explore</Link></li>
                <li><Link to="/explore">Public directory</Link></li>
                <li><Link to="/news">News</Link></li>
                <li><Link to="/register">Request access</Link></li>
              </ul>
            </div>
            <div>
              <span className="wo-eyebrow">Members</span>
              <ul className="site-footer__list">
                <li><Link to="/login">Sign in</Link></li>
                <li><Link to="/forgot-password">Reset password</Link></li>
                <li><Link to="/help">Contact support</Link></li>
              </ul>
            </div>
            <div>
              <span className="wo-eyebrow">Legal</span>
              <ul className="site-footer__list">
                <li><Link to="/legal/terms">Terms</Link></li>
                <li><Link to="/legal/privacy">Privacy</Link></li>
                <li><Link to="/legal/conduct">Code of conduct</Link></li>
              </ul>
            </div>
          </div>
          <p className="caption" style={{ marginTop: "var(--space-12)", color: "var(--text-on-brand-muted)" }}>
            &copy; {new Date().getFullYear()} WO Community, the member platform of WithOnyeka.
          </p>
          <div className="site-footer__mark" aria-hidden="true">
            WO COMMUNITY
          </div>
          </div>
        </div>
      </footer>
    </>
  );
}
