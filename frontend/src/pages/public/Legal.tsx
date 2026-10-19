import { Link, useParams } from "react-router-dom";
import { Alert } from "../../components";
import { PageHeader } from "../../ui/blocks";
import conduct from "./legal/conduct.md?raw";
import { LegalText, parse } from "./legal/LegalText";
import privacy from "./legal/privacy.md?raw";
import terms from "./legal/terms.md?raw";

// When the current wording took effect. Change both when the text changes, and keep the old version.
const EFFECTIVE = "19 October 2026";
const UPDATED = "19 October 2026";

const DOCS: Record<string, { title: string; intro: string; source: string }> = {
  terms: {
    title: "Terms and Conditions",
    intro: "The agreement between you and WO Community for using the platform.",
    source: terms,
  },
  privacy: {
    title: "Privacy Policy",
    intro: "What personal data we collect, how we use and protect it, and the rights you have.",
    source: privacy,
  },
  conduct: {
    title: "Code of Conduct",
    intro: "How we expect everyone in the community to behave, and what happens when someone gets it wrong.",
    source: conduct,
  },
};

/** The full text of each policy, with its dates and a list of sections to jump to. */
export function Legal() {
  const { doc = "" } = useParams();
  const page = DOCS[doc];
  if (!page) {
    return (
      <div className="wo-container wo-container--narrow" style={{ padding: "var(--space-16) var(--page-margin)" }}>
        <Alert tone="warning" title="We could not find that page">
          Try the <Link className="app-link" to="/">home page</Link>.
        </Alert>
      </div>
    );
  }
  const sections = parse(page.source).flatMap((b) => (b.kind === "heading" ? [b] : []));
  return (
    <div className="wo-container wo-container--narrow wo-legal" style={{ padding: "var(--space-12) var(--page-margin) var(--space-24)" }}>
      <PageHeader eyebrow="Legal" title={page.title} lead={page.intro} />
      <p className="wo-legal__dates">
        <span><strong>Effective date:</strong> {EFFECTIVE}</span>
        <span><strong>Last updated:</strong> {UPDATED}</span>
      </p>
      <nav className="wo-legal__toc" aria-label="Sections">
        <details>
          <summary>Contents</summary>
          <ol>
            {sections.map((s) => (
              <li key={s.id}><a href={`#${s.id}`}>{s.text}</a></li>
            ))}
          </ol>
        </details>
      </nav>
      <LegalText source={page.source} />
      <nav className="wo-legal__others" aria-label="Other policies">
        {Object.entries(DOCS)
          .filter(([key]) => key !== doc)
          .map(([key, other]) => (
            <Link key={key} className="app-link" to={`/legal/${key}`}>{other.title}</Link>
          ))}
      </nav>
    </div>
  );
}
