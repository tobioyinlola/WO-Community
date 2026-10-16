import { Award, Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { useDocumentTitle } from "../../ui/blocks";
import { ArrowCircle } from "../../ui/ArrowCircle";
import { Reveal } from "../../ui/Reveal";

const STATS = [
  { value: "30+", label: "Global awards" },
  { value: "200+", label: "Entrepreneurs mentored" },
  { value: "15,000+", label: "Attendees at his talks" },
  { value: "18+", label: "Portfolio companies" },
  { value: "500+", label: "People hired into his companies" },
  { value: "4M+", label: "Customers served on 3 continents" },
];

/** The four roles, each a picture that carries its own title and figures. */
const ROLES = [
  {
    src: "/brand/founder/role-entrepreneur.webp",
    alt: "Award-Winning Entrepreneur. Onyeka's ambition to deliver value through his startups has earned him more than 30 global awards. 30+ Global Awards.",
  },
  {
    src: "/brand/founder/role-speaker.webp",
    alt: "Global Speaker. With more than 15,000 attendees, Onyeka is one of Africa's most sought-after speakers of his generation. 15,000+ Attendees.",
  },
  {
    src: "/brand/founder/role-mentor.webp",
    alt: "All-Star Mentor and Coach. With over 200 entrepreneurs mentored, Onyeka has been recognized as an all-star mentor by Techstars. 200+ Entrepreneurs.",
  },
  {
    src: "/brand/founder/role-investor.webp",
    alt: "Angel Investor and Advisor. Always seeking opportunities to support value-driven startups, with more than 18 portfolio companies. 18+ Portfolio Companies.",
  },
];

const RECOGNITIONS = [
  "2024 Africa's Top 40 CEOs Under 40",
  "All-Star Mentor 2023, Techstars Global",
  "50 African Innovators, Global Shakers",
  "100 Most Influential Africans, The African Report",
  "African Leadership Person of the Year Award, African Business Report",
  "JCI Ten Outstanding Persons of Nigeria, Junior Chambers International",
  "Internet Entrepreneur of the Year, Business Insider Africa",
  "Entrepreneur of the Year, The GAGE Awards",
];

const PRINCIPLES: Array<{ before: string; strong: string; after: string }> = [
  {
    before: "We are all ",
    strong: "products of our history and environment",
    after: " which influences our decisions daily. We can not change our history, but we can change our future with the decisions you make today.",
  },
  {
    before: "There is ",
    strong: "no one on Earth that deserves where they are born",
    after: ". With this knowledge, treat all mankind with respect and humility.",
  },
  {
    before: "The world is a cycle of seasons. ",
    strong: "My life is a cycle of seasons",
    after: " as well. I chose not to waste any season I find myself because they contain lessons to guide me in making the best decisions for my season tomorrow.",
  },
  {
    before: "Lead with love and ",
    strong: "enjoy every moment with laughter and a positive mindset",
    after: ".",
  },
];

/** About the founder: who started WO Community, what he has built, and what he stands for. */
export function Founder() {
  useDocumentTitle("About the founder");
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <>
      <section className="site-band founder-hero" aria-labelledby="founder-title">
        <div className="wo-container founder-hero__grid">
          <div>
            <p className="wo-eyebrow">About the founder</p>
            <h1 className="display-lg founder-hero__title" id="founder-title">
              Onyeka <span className="site-chip">Akumah</span>
            </h1>
            <p className="founder-hero__lead">
              Onyeka Akumah is one of Africa's most celebrated entrepreneurs for his exploits of building successful startups in his personal capacity as a founder or as part of the senior leadership team of global businesses. With over 500 individuals recruited directly to work in his companies, he has built startups in the Transportation, Real Estate, Agriculture, Marketing, E-commerce, Fintech, Travel, and Hospitality industries. He is also a marketing, investor relations, and product development expert who has directly served over 4 million customers across 3 continents.
            </p>
            <p className="founder-hero__body">
              Onyeka Akumah is also a coach and global speaker empowering the next generation of entrepreneurs with the right tools and skills to create value-driven businesses. For his work as a mentor and coach, he was recently appointed as a lecturer in Rome Business School and won the All-Star Mentor Award from the largest seed-stage accelerator in the world, Techstars. Onyeka has successfully mentored more than 200 entrepreneurs in the last 5 years.
            </p>
          </div>
          <figure className="founder-photo">
            <img src="/brand/founder/award-stage.webp" alt="Onyeka Akumah on stage receiving an African Startup Award" width={768} height={530} />
            <figcaption>Receiving an African Startup Award</figcaption>
          </figure>
        </div>
        <div className="wo-container">
          <ul className="founder-stats" aria-label="Onyeka in numbers">
            {STATS.map((s) => (
              <li key={s.label}>
                <strong>{s.value}</strong>
                <span>{s.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="site-band" aria-labelledby="founder-roles">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">What he does</span>
          </div>
          <h2 className="display-md" id="founder-roles" style={{ margin: "var(--space-8) 0 var(--space-10)" }}>
            Builder, speaker, <span className="site-chip">mentor</span>, investor
          </h2>
          <Reveal as="ul" className="founder-roles">
            {ROLES.map((role) => (
              <li key={role.src}>
                <img src={role.src} alt={role.alt} width={406} height={528} loading="lazy" decoding="async" />
              </li>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="site-band site-band--subtle" aria-labelledby="founder-awards">
        <div className="wo-container founder-awards">
          <div>
            <h2 className="founder-awards__title" id="founder-awards">
              <Award size={28} strokeWidth={1.5} aria-hidden="true" />
              <span>
                30+ <em>Global Awards</em> won for his entrepreneurial contributions
              </span>
            </h2>
            <figure className="founder-cover">
              <img src="/brand/founder/business-elites-africa.webp" alt="Cover of Business Elites Africa, issue 116: 40 under 40 trailblazing African entrepreneurs, featuring Onyeka Akumah" width={362} height={468} loading="lazy" decoding="async" />
              <figcaption>On the cover of Business Elites Africa: 40 Under 40 Trailblazing African Entrepreneurs</figcaption>
            </figure>
          </div>
          <div>
            <h3 className="founder-list__title">Recent top recognitions</h3>
            <ul className="founder-list">
              {RECOGNITIONS.map((r) => (
                <li key={r}>
                  <Award size={20} strokeWidth={1.5} aria-hidden="true" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="site-band" aria-labelledby="founder-principles">
        <div className="wo-container founder-awards">
          <h2 className="founder-awards__title" id="founder-principles">
            <Compass size={28} strokeWidth={1.5} aria-hidden="true" />
            <span>His personal guiding principles</span>
          </h2>
          <ul className="founder-list founder-list--principles">
            {PRINCIPLES.map((p) => (
              <li key={p.strong}>
                <Compass size={20} strokeWidth={1.5} aria-hidden="true" />
                <span>
                  {p.before}
                  <strong>{p.strong}</strong>
                  {p.after}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="site-band" aria-labelledby="founder-join">
        <div className="wo-container">
          <div className="founder-join wo-on-brand">
            <h2 className="display-md" id="founder-join" style={{ margin: 0 }}>
              Build with the community he <span className="site-chip">founded</span>
            </h2>
            <p>
              WO Community brings founders together with mentors, a launch toolkit and an AI advisor that coaches the way Onyeka does.
            </p>
            <Link className="wo-btn wo-btn--accent" to={signedIn ? "/app" : "/register"}>
              {signedIn ? "Go to the community" : "Request access"}
              <ArrowCircle />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
