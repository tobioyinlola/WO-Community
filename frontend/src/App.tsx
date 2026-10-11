import { Design } from "./pages/Design";
import { Button } from "./components";

/** Routing is added with the first product screens; for now there is the system itself. */
export function App() {
  if (window.location.pathname.startsWith("/design")) return <Design />;
  return (
    <main className="wo-container wo-container--narrow" style={{ paddingTop: "var(--space-24)" }}>
      <div className="wo-page-rule">
        <hr />
        <span className="wo-eyebrow">WO Community</span>
      </div>
      <h1 className="h1" style={{ margin: "var(--space-8) 0 var(--space-4)" }}>
        Welcome
      </h1>
      <p className="body-lg" style={{ color: "var(--text-secondary)" }}>
        The member platform is being built. The design system is available now.
      </p>
      <div className="wo-row" style={{ marginTop: "var(--space-6)" }}>
        <a href="/design" style={{ textDecoration: "none" }}>
          <Button>View the design system</Button>
        </a>
      </div>
    </main>
  );
}
