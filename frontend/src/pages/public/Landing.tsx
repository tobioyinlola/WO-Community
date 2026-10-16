import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Briefcase,
  CalendarDays,
  Check,
  GraduationCap,
  Rocket,
  UserCheck,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Card, CardTo, CardText, CardTitle, Logo } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { Section, useDocumentTitle } from "../../ui/blocks";
import { ArrowCircle } from "../../ui/ArrowCircle";
import { Carousel } from "../../ui/Carousel";
import { CountryMarquee } from "../../ui/CountryMarquee";
import { CountUp } from "../../ui/CountUp";
import { Faq } from "../../ui/Faq";
import { MediaPlaceholder } from "../../ui/MediaPlaceholder";
import { TestimonialMarquee } from "../../ui/TestimonialMarquee";
import { Reveal } from "../../ui/Reveal";
import { COMPARE, FAQ, STEPS, MARQUEE_COUNTRIES } from "./landingContent";

interface Feature {
  icon: LucideIcon;
  title: string;
  text: string;
  /** The area of the community the card is about. */
  tag: string;
  /** The card's photo, under public/brand/features, and what it shows for screen readers. */
  photo: string;
  photoAlt: string;
  /** Where a visitor can go: the public page where there is one, otherwise a request for access. */
  to: string;
  cta: string;
}

const FEATURES: Feature[] = [
  {
    icon: Users,
    tag: "Directory",
    photo: "/brand/features/directory.webp",
    photoAlt: "Founders talking together at a community meetup",
    to: "/explore?tab=founders",
    cta: "Explore",
    title: "Find your people",
    text: "A directory of founders, operators and investors across the continent, searchable by what they do and where.",
  },
  {
    icon: UserCheck,
    tag: "Mentors",
    photo: "/brand/features/mentors.webp",
    photoAlt: "A mentor and a founder in a one to one conversation",
    to: "/register",
    cta: "Request access",
    title: "Learn from people who did it",
    text: "Book a session with a vetted mentor. Real experience, one conversation at a time.",
  },
  {
    icon: Rocket,
    tag: "Launch toolkit",
    photo: "/brand/features/launch-toolkit.webp",
    photoAlt: "A founder working on a business plan at a laptop",
    to: "/register",
    cta: "Request access",
    title: "Launch with a plan",
    text: "Score your idea, write the plan, model the numbers and build the deck, all in one private workspace.",
  },
  {
    icon: GraduationCap,
    tag: "Courses",
    photo: "/brand/features/courses.webp",
    photoAlt: "Founders learning together in a workshop",
    to: "/explore?tab=courses",
    cta: "Explore",
    title: "Keep learning",
    text: "Practical courses on foundations, fundraising and growth, with certificates you can share.",
  },
  {
    icon: Briefcase,
    tag: "Jobs",
    photo: "/brand/features/jobs.webp",
    photoAlt: "A startup team at work",
    to: "/explore?tab=jobs",
    cta: "Explore",
    title: "Hire and get hired",
    text: "A job board where every role comes from someone in the community.",
  },
  {
    icon: CalendarDays,
    tag: "Events",
    photo: "/brand/features/events.webp",
    photoAlt: "A founder pitching on stage at a demo day",
    to: "/explore?tab=events",
    cta: "Explore",
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

/** The numbers shown, each a count of public pages that the tile links to. */
const STAT_TILES = [
  { key: "startups", label: "Startups listed", to: "/explore?tab=startups" },
  { key: "founders", label: "Founders listed", to: "/explore?tab=founders" },
  { key: "courses", label: "Courses open to visitors", to: "/explore?tab=courses" },
  { key: "jobs", label: "Open roles", to: "/explore?tab=jobs" },
] as const;

export function Landing() {
  useDocumentTitle("");
  const { status } = useAuth();
  // Only words members really said, published by the team with their permission.
  const testimonials = useQuery({
    queryKey: ["public", "testimonials"],
    queryFn: () => unwrap(api.GET("/api/v1/public/testimonials")),
    staleTime: 10 * 60_000,
  });
  const voices = testimonials.data ?? [];
  const events = useQuery({
    queryKey: ["public", "events", "home"],
    queryFn: () => unwrap(api.GET("/api/v1/public/events", { params: { query: { limit: 3 } } })),
  });
  const news = useQuery({
    queryKey: ["public", "news", "home"],
    queryFn: () => unwrap(api.GET("/api/v1/public/news", { params: { query: { limit: 3 } } })),
  });
  const stats = useQuery({
    queryKey: ["public", "stats"],
    queryFn: () => unwrap(api.GET("/api/v1/public/stats")),
    staleTime: 10 * 60 * 1000,
  });
  const signedIn = status === "authenticated";
  const tiles = STAT_TILES.filter((tile) => (stats.data?.[tile.key] ?? 0) > 0);

  return (
    <>
      <section className="site-hero wo-on-brand" aria-labelledby="hero-title">
        <div className="wo-container">
          <div className="site-hero__card wo-on-brand">
          <div className="site-hero__grid">
            <div className="site-hero__copy">
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
                    <ArrowCircle />
                  </Link>
                ) : (
                  <>
                    <Link className="wo-btn wo-btn--accent wo-btn--lg" to="/register">
                      Request access
                      <ArrowCircle />
                    </Link>
                    <Link className="wo-btn wo-btn--on-brand wo-btn--lg" to="/login">
                      Sign in
                    </Link>
                  </>
                )}
              </div>
            </div>
            <div className="site-hero__art" aria-hidden="true">
              <div className="site-hero__frame">
                <Logo on="dark" kind="mark" height={140} />
              </div>
              <svg className="site-hero__line" viewBox="0 0 400 500" fill="none" focusable="false">
                <path pathLength="1" d="M30 492 V210 A170 170 0 0 1 370 210 V492" />
                <path pathLength="1" d="M86 498 C150 470 250 470 314 498" />
              </svg>
            </div>
          </div>
          </div>
        </div>
      </section>

      <section className="site-band site-band--marquee" aria-labelledby="countries">
        <div className="wo-container">
          <h2 className="site-marquee__title" id="countries">
            Founders in our community are from
          </h2>
        </div>
        <CountryMarquee countries={MARQUEE_COUNTRIES.map((code) => ({ code, founders: 0 }))} />
      </section>

      {tiles.length >= 2 ? (
        <section className="site-band site-band--tight" aria-labelledby="numbers">
          <div className="wo-container">
            <div className="wo-page-rule">
              <hr />
              <span className="wo-eyebrow">The community in numbers</span>
            </div>
            <h2 className="wo-visually-hidden" id="numbers">
              The community in numbers
            </h2>
            <Reveal className={`site-stats site-stats--${tiles.length}`}>
              {tiles.map((tile, index) => (
                <Link key={tile.key} to={tile.to} className={`site-stat site-stat--${index === 0 ? "feature" : index === 1 ? "white" : "plain"}`}>
                  <span className="site-stat__num">
                    <CountUp value={stats.data?.[tile.key] ?? 0} />
                  </span>
                  <span className="site-stat__label">{tile.label}</span>
                  <span className="site-stat__go" aria-hidden="true">
                    <ArrowRight size={18} strokeWidth={2} />
                  </span>
                </Link>
              ))}
            </Reveal>
          </div>
        </section>
      ) : null}

      <section className="site-band" aria-labelledby="why">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">What you get</span>
          </div>
          <h2 className="display-md" id="why" style={{ margin: "var(--space-8) 0 var(--space-12)" }}>
            Everything a founder needs, <span className="site-chip">in one place</span>
          </h2>
          <Carousel label="What you get">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="site-carousel__slide">
                <Card className="site-feature">
                  <div className="site-feature__media">
                    <MediaPlaceholder icon={feature.icon} src={feature.photo} alt={feature.photoAlt} />
                    <span className="site-feature__tag">{feature.tag}</span>
                  </div>
                  <span className="app-tile site-feature__badge">
                    <feature.icon size={24} strokeWidth={1.5} aria-hidden="true" />
                  </span>
                  <CardTitle>{feature.title}</CardTitle>
                  <CardText>{feature.text}</CardText>
                  <Link className="wo-btn wo-btn--primary wo-btn--sm site-feature__cta" to={feature.to} aria-label={`${feature.cta}: ${feature.title}`}>
                    {feature.cta}
                    <ArrowCircle />
                  </Link>
                </Card>
              </li>
            ))}
          </Carousel>
        </div>
      </section>

      <section className="site-band" aria-labelledby="how">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">Getting started</span>
          </div>
          <h2 className="display-md" id="how" style={{ margin: "var(--space-8) 0 var(--space-12)" }}>
            From request to <span className="site-chip">member</span>
          </h2>
          <Reveal as="ol" className="site-steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="site-step">
                <span className="site-step__n" aria-hidden="true">
                  {index + 1}
                </span>
                <h3 className="site-step__title">{step.title}</h3>
                <p className="site-step__text">{step.text}</p>
              </li>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="site-band" aria-labelledby="alone">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">Why join</span>
          </div>
          <h2 className="display-md" id="alone" style={{ margin: "var(--space-8) 0 var(--space-12)" }}>
            On your own, or <span className="site-chip">in the community</span>
          </h2>
          <Reveal as="ul" className="site-compare">
            {COMPARE.map((pair, index) => (
              <li key={pair.problem} className="site-compare__row">
                <div className="site-compare__card site-compare__card--problem">
                  <span className="site-compare__head">
                    <span className="site-compare__n" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="site-compare__mark site-compare__mark--no" aria-hidden="true">
                      <X size={18} strokeWidth={2.5} />
                    </span>
                  </span>
                  <p>
                    <span className="wo-visually-hidden">On your own: </span>
                    {pair.problem}
                  </p>
                </div>
                <span className="site-compare__arrow" aria-hidden="true">
                  <ArrowRight size={22} strokeWidth={2} />
                </span>
                <div className="site-compare__card site-compare__card--solution">
                  <span className="site-compare__head">
                    <span className="site-compare__n" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="site-compare__mark site-compare__mark--yes" aria-hidden="true">
                      <Check size={18} strokeWidth={2.5} />
                    </span>
                  </span>
                  <p>
                    <span className="wo-visually-hidden">In the community: </span>
                    {pair.solution}
                  </p>
                </div>
              </li>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="site-band site-band--subtle" aria-labelledby="members-get">
        <div className="wo-container">
          <Reveal className="app-split app-split--even site-cta">
            <div className="site-cta__intro">
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
            <Card variant="brand" className="site-cta__card">
              <span className="wo-eyebrow">Intentional</span>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Every member is reviewed</CardTitle>
              <CardText>
                Admission is by application so the rooms stay useful. Tell us what you are building and
                an admin will reply by email.
              </CardText>
              <div style={{ marginTop: "var(--space-6)" }}>
                <Link className="wo-btn wo-btn--accent" to="/register">
                  Request access
                  <ArrowCircle />
                </Link>
              </div>
            </Card>
          </Reveal>
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
              <Reveal className="app-grid">
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
              </Reveal>
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
              <Reveal className="app-grid">
                {news.data.results.map((item) => (
                  <CardTo key={item.slug} to={`/news/${item.slug}`}>
                    <Badge variant="operator">{humanise(item.type)}</Badge>
                    <CardTitle style={{ marginTop: "var(--space-3)" }}>{item.title}</CardTitle>
                    <CardText>{formatDate(item.published_at)}</CardText>
                  </CardTo>
                ))}
              </Reveal>
            ) : (
              <p className="body app-muted">Stories from members and the team appear here.</p>
            )}
          </Section>
        </div>
      </section>

      <section className="site-band" aria-labelledby="faq-title">
        <div className="wo-container wo-container--narrow">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">Questions</span>
          </div>
          <h2 className="display-md" id="faq-title" style={{ margin: "var(--space-8) 0 var(--space-10)" }}>
            Questions, <span className="site-chip">answered</span>
          </h2>
          <Faq items={FAQ} />
        </div>
      </section>

      {voices.length > 0 ? (
        <section className="site-band" aria-labelledby="voices">
          <div className="wo-container">
            <div className="wo-page-rule">
              <hr />
              <span className="wo-eyebrow">Members</span>
            </div>
            <h2 className="display-md" id="voices" style={{ margin: "var(--space-8) 0 var(--space-10)" }}>
              In their <span className="site-chip">own words</span>
            </h2>
          </div>
          <TestimonialMarquee items={voices} />
        </section>
      ) : null}
    </>
  );
}
