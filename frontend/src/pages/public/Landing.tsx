import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CalendarDays,
  GraduationCap,
  Rocket,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Card, CardTo, CardText, CardTitle, Logo } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { Section, useDocumentTitle } from "../../ui/blocks";

interface Feature {
  icon: LucideIcon;
  title: string;
  text: string;
}

const FEATURES: Feature[] = [
  {
    icon: Users,
    title: "Find your people",
    text: "A directory of founders, operators and investors across the continent, searchable by what they do and where.",
  },
  {
    icon: UserCheck,
    title: "Learn from people who did it",
    text: "Book a session with a vetted mentor. Real experience, one conversation at a time.",
  },
  {
    icon: Rocket,
    title: "Launch with a plan",
    text: "Score your idea, write the plan, model the numbers and build the deck, all in one private workspace.",
  },
  {
    icon: GraduationCap,
    title: "Keep learning",
    text: "Practical courses on foundations, fundraising and growth, with certificates you can share.",
  },
  {
    icon: Briefcase,
    title: "Hire and get hired",
    text: "A job board where every role comes from someone in the community.",
  },
  {
    icon: CalendarDays,
    title: "Meet in person",
    text: "Demo days, workshops and meetups, with registration and reminders built in.",
  },
];

const GET = [
  "A profile that tells your story, with you in control of who sees what",
  "Introductions to mentors who have built what you are building",
  "A private launch toolkit: validation score, business plan, forecast, deck and prototype",
  "First access to demo days, programmes and funding news",
];

export function Landing() {
  useDocumentTitle("");
  const { status } = useAuth();
  const events = useQuery({
    queryKey: ["public", "events", "home"],
    queryFn: () => unwrap(api.GET("/api/v1/public/events", { params: { query: { limit: 3 } } })),
  });
  const news = useQuery({
    queryKey: ["public", "news", "home"],
    queryFn: () => unwrap(api.GET("/api/v1/public/news", { params: { query: { limit: 3 } } })),
  });
  const signedIn = status === "authenticated";

  return (
    <>
      <section className="site-hero wo-on-brand" aria-labelledby="hero-title">
        <div className="wo-container">
          <div className="site-hero__grid">
            <div>
              <span className="wo-eyebrow">WO Community</span>
              <h1 className="display-xl site-hero__title" id="hero-title">
                The future of Africa is being <span className="wo-hl">built</span> here.
              </h1>
              <p className="body-lg site-hero__lead">
                We are not just a community. We are a launchpad for world-class African startups: a
                place for founders, operators and investors to meet, learn and build, on purpose.
              </p>
              <div className="app-cluster">
                {signedIn ? (
                  <Link className="wo-btn wo-btn--accent wo-btn--lg" to="/app">
                    Open the app
                  </Link>
                ) : (
                  <>
                    <Link className="wo-btn wo-btn--accent wo-btn--lg" to="/register">
                      Request access
                    </Link>
                    <Link className="wo-btn wo-btn--on-brand wo-btn--lg" to="/login">
                      Sign in
                    </Link>
                  </>
                )}
              </div>
            </div>
            <div className="site-hero__frame" aria-hidden="true">
              <Logo on="dark" kind="mark" height={140} />
            </div>
          </div>
        </div>
      </section>

      <section className="site-band" aria-labelledby="why">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">What you get</span>
          </div>
          <h2 className="display-md" id="why" style={{ margin: "var(--space-8) 0 var(--space-12)" }}>
            Everything a founder needs, <span style={{ color: "var(--text-accent)" }}>in one place</span>
          </h2>
          <div className="app-grid">
            {FEATURES.map((feature) => (
              <Card key={feature.title}>
                <span className="app-tile" style={{ marginBottom: "var(--space-4)" }}>
                  <feature.icon size={24} strokeWidth={1.5} aria-hidden="true" />
                </span>
                <CardTitle>{feature.title}</CardTitle>
                <CardText>{feature.text}</CardText>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="site-band site-band--subtle" aria-labelledby="members-get">
        <div className="wo-container">
          <div className="app-split app-split--even">
            <div>
              <span className="wo-eyebrow">Membership</span>
              <h2 className="display-sm" id="members-get" style={{ margin: "var(--space-4) 0 var(--space-6)" }}>
                Built for people who build
              </h2>
              <ul className="site-bullets">
                {GET.map((line) => (
                  <li key={line}>
                    <span className="wo-plus" aria-hidden="true" />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
            <Card variant="brand">
              <span className="wo-eyebrow">Intentional</span>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Every member is reviewed</CardTitle>
              <CardText>
                Admission is by application so the rooms stay useful. Tell us what you are building and
                an admin will reply by email.
              </CardText>
              <div style={{ marginTop: "var(--space-6)" }}>
                <Link className="wo-btn wo-btn--accent" to="/register">
                  Request access
                </Link>
              </div>
            </Card>
          </div>
        </div>
      </section>

      <section className="site-band" aria-label="What is happening">
        <div className="wo-container">
          <Section
            title="Coming up"
            action={
              <Link className="app-linklike" to="/explore">
                See everything
              </Link>
            }
          >
            {events.data && events.data.results.length > 0 ? (
              <div className="app-grid">
                {events.data.results.map((event) => (
                  <CardTo key={event.slug} to="/explore?tab=events">
                    <Badge variant="investor">{humanise(event.type)}</Badge>
                    <CardTitle style={{ marginTop: "var(--space-3)" }}>{event.title}</CardTitle>
                    <CardText>
                      {formatDate(event.starts_at)}
                      {event.location ? `, ${event.location}` : ""}
                    </CardText>
                  </CardTo>
                ))}
              </div>
            ) : (
              <p className="body app-muted">New events are announced here as soon as they are set.</p>
            )}
          </Section>
          <Section
            title="From the community"
            action={
              <Link className="app-linklike" to="/news">
                All news
              </Link>
            }
          >
            {news.data && news.data.results.length > 0 ? (
              <div className="app-grid">
                {news.data.results.map((item) => (
                  <CardTo key={item.slug} to={`/news/${item.slug}`}>
                    <Badge variant="operator">{humanise(item.type)}</Badge>
                    <CardTitle style={{ marginTop: "var(--space-3)" }}>{item.title}</CardTitle>
                    <CardText>{formatDate(item.published_at)}</CardText>
                  </CardTo>
                ))}
              </div>
            ) : (
              <p className="body app-muted">Stories from members and the team appear here.</p>
            )}
          </Section>
        </div>
      </section>
    </>
  );
}
