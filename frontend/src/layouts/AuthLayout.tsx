import { Link, Outlet } from "react-router-dom";
import { Logo } from "../components";

/** Two panels: the brand on forest, and the form on cream. On phones the forest panel is gone and the logo sits above the form. */
export function AuthLayout() {
  return (
    <div className="auth-page">
      <aside className="auth-brand wo-on-brand">
        <Link to="/" aria-label="WO Community, home">
          <Logo on="dark" height={48} />
        </Link>
        <blockquote className="auth-brand__quote">
          <p className="display-md">
            The future of Africa is being <span className="wo-hl">built</span> here.
          </p>
          <p className="body-lg" style={{ color: "var(--text-on-brand-muted)", marginTop: "var(--space-6)" }}>
            Founders, operators and investors who choose to build in the open, together.
          </p>
        </blockquote>
        <p className="caption" style={{ color: "var(--text-on-brand-muted)", margin: 0 }}>
          WO Community, the member platform of WithOnyeka.
        </p>
      </aside>
      <main className="auth-panel" id="main">
        <Link to="/" className="auth-panel__logo" aria-label="WO Community, home">
          <Logo on="auto" height={40} />
        </Link>
        <div className="auth-card">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
