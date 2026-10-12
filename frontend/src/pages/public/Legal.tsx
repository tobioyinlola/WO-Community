import { Link, useParams } from "react-router-dom";
import { Alert } from "../../components";
import { PageHeader } from "../../ui/blocks";

const DOCS: Record<string, { title: string; intro: string; points: string[] }> = {
  terms: {
    title: "Terms of membership",
    intro: "The agreement between you and WO Community.",
    points: [
      "Membership is by application and can be ended by either side.",
      "You are responsible for what you post and for keeping your sign in safe.",
      "The community team may remove content or accounts that break these terms.",
    ],
  },
  privacy: {
    title: "Privacy policy",
    intro: "What we hold about you and how you stay in control of it.",
    points: [
      "You choose who can see each part of your profile: public, members only, or private.",
      "Content in your private launch workspace is yours. It is never shown to other members and never used to train models.",
      "You can download everything we hold about you, and delete your account.",
    ],
  },
  conduct: {
    title: "Code of conduct",
    intro: "How we treat each other.",
    points: [
      "Be direct and kind. Disagree with ideas, never with people.",
      "Do not misrepresent your results, your team or your funding.",
      "Respect privacy: what is shared in a mentoring session stays there.",
    ],
  },
};

/** A readable summary of each policy. The binding wording comes from the community team. */
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
  return (
    <div className="wo-container wo-container--narrow" style={{ padding: "var(--space-12) var(--page-margin) var(--space-24)" }}>
      <PageHeader eyebrow="Legal" title={page.title} lead={page.intro} />
      <ul className="site-bullets">
        {page.points.map((point) => (
          <li key={point}>
            <span className="wo-plus" aria-hidden="true" />
            <span>{point}</span>
          </li>
        ))}
      </ul>
      <div style={{ marginTop: "var(--space-8)" }}>
        <Alert tone="info" title="Summary only">
          This page summarises the policy. The community team publishes the full, binding text.
        </Alert>
      </div>
    </div>
  );
}
