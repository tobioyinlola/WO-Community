import { Link, NavLink, Outlet } from "react-router-dom";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { Logo } from "../components";

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/explore", label: "Explore" },
  { to: "/news", label: "News" },
];

/** The public site: a forest band header, the page, and a forest footer. */
export function PublicLayout() {
  const { status } = useAuth();
  const [open, setOpen] = useState(false);
  const signedIn = status === "authenticated";

  return (
    <>
      <a href="#main" className="wo-visually-hidden">
        Skip to content
      </a>
      <nav className="wo-nav wo-nav--brand wo-on-brand site-head" aria-label="Main">
        <Link to="/" aria-label="WO Community, home">
          <Logo on="dark" height={40} />
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
        <div id="site-panel" className="wo-nav__panel" data-open={open}>
          <ul className="wo-nav__links">
            {LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.end}
                  className="wo-nav__link"
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="wo-nav__tail">
            {signedIn ? (
              <Link className="wo-btn wo-btn--accent wo-btn--sm" to="/app">
                Open the app
              </Link>
            ) : (
              <>
                <Link className="wo-btn wo-btn--on-brand wo-btn--sm" to="/login">
                  Sign in
                </Link>
                <Link className="wo-btn wo-btn--accent wo-btn--sm" to="/register">
                  Request access
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
          <div className="site-footer__grid">
            <div>
              <Logo on="dark" height={44} />
              <p className="body" style={{ maxWidth: "36ch", marginTop: "var(--space-4)", color: "var(--text-on-brand-muted)" }}>
                Africa&rsquo;s most intentional founder, operator and investor ecosystem.
              </p>
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
        </div>
      </footer>
    </>
  );
}
