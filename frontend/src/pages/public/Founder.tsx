import { Compass, ExternalLink, Linkedin } from "lucide-react";
import { useState } from "react";
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
  { value: "6M+", label: "Customers served" },
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

const BOOK_URL = "https://www.amazon.ca/Zero-Forty-Dont-Stop-Building/dp/B0DR8YQB71";

interface Person {
  name: string;
  role: string;
  linkedin: string;
  /**
   * Their LinkedIn profile photo. LinkedIn issues these addresses without an expiry date; if one
   * stops loading (say they change their photo) the card falls back to their initials.
   */
  photo?: string;
}

const TEAM: Person[] = [
  {
    name: "Olusola Osinoiki",
    role: "Partner",
    linkedin: "https://www.linkedin.com/in/solaosinoiki/",
    photo: "https://media.licdn.com/dms/image/v2/D4E03AQFE8ye0PGD1cg/profile-displayphoto-shrink_200_200/profile-displayphoto-shrink_200_200/0/1704980471293?e=2147483647&v=beta&t=HdZ0pIl2F5EuPcNRd2oYD0W4HLmPG1KIGDyzoi-wc7w",
  },
  {
    name: "Temitope Ekundayo",
    role: "Community Advisor",
    linkedin: "https://www.linkedin.com/in/temitope-ekundayo-/",
    photo: "https://media.licdn.com/dms/image/v2/D4D03AQHtdvs5wjgi7Q/profile-displayphoto-shrink_200_200/profile-displayphoto-shrink_200_200/0/1693494605335?e=2147483647&v=beta&t=AJ3k0Rqry9MD59nGxuVNW4FOOhTLf2ZV1gA2q-ozyrE",
  },
  { name: "Thara Atta", role: "Community Manager", linkedin: "https://www.linkedin.com/in/thara-atta-48297513b/" },
  {
    name: "Enianu Eniafe",
    role: "Community Support Team",
    linkedin: "https://www.linkedin.com/in/enianu-eniafe/",
    photo: "https://media.licdn.com/dms/image/v2/D4D03AQGK6ws3erbU8A/profile-displayphoto-scale_200_200/B4DZuMZPDZHwAY-/0/1767586985202?e=2147483647&v=beta&t=23jqMJUkSe6Y8WXimE8-hkuTO8fEIWg5IfEG6TtCMgk",
  },
  {
    name: "James Samuel Ihima",
    role: "Community Support Team",
    linkedin: "https://www.linkedin.com/in/james-ihima-450597272/",
    photo: "https://media.licdn.com/dms/image/v2/D4E03AQG1bo6QLCEQSw/profile-displayphoto-scale_200_200/B4EZ89WqDwHkAc-/0/1783440779045?e=2147483647&v=beta&t=ngH5Ssq8U9mUI2uOLmWSOGOIBRCg3je06-zT59YvlVQ",
  },
  {
    name: "Justus Oyinlola",
    role: "Tech Support",
    linkedin: "https://www.linkedin.com/in/justusoyinlola/",
    photo: "https://media.licdn.com/dms/image/v2/D4E03AQHfMIuZanwPOw/profile-displayphoto-scale_200_200/B4EZpBb5V8GYAY-/0/1762034425748?e=2147483647&v=beta&t=gHBWONooG88Gu7DNQ46Z6ShloHhtYfThNmADa0oUrhU",
  },
];

/** Their photo, or their initials when the photo has not been added or does not load. */
function PersonPhoto({ person }: { person: Person }) {
  const [failed, setFailed] = useState(false);
  const initials = person.name.split(" ").filter(Boolean).map((w) => w[0]).slice(0, 2).join("");
  return person.photo && !failed ? (
    <img className="founder-person__photo" src={person.photo} alt="" width={96} height={96} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  ) : (
    <span className="founder-person__photo founder-person__photo--initials" aria-hidden="true">{initials}</span>
  );
}

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
              Onyeka Akumah is one of Africa's most celebrated entrepreneurs for his exploits of building successful startups in his personal capacity as a founder or as part of the senior leadership team of global businesses. With over 500 individuals recruited directly to work in his companies, he has built startups in the Transportation, Real Estate, Agriculture, Marketing, E-commerce, Fintech, Travel, and Hospitality industries. He is also a marketing, investor relations, and product development expert who has directly served over 6 million customers across Canada, Nigeria, Kenya, Ghana, Uganda and the United Arab Emirates.
            </p>
            <p className="founder-hero__body">
              Onyeka Akumah is also a coach and global speaker empowering the next generation of entrepreneurs with the right tools and skills to create value-driven businesses. For his work as a mentor and coach, he was recently appointed as a lecturer in Rome Business School and won the All-Star Mentor Award from the largest seed-stage accelerator in the world, Techstars. Onyeka has successfully mentored more than 200 entrepreneurs in the last 5 years.
            </p>
            <p className="founder-hero__body">
              He is also the author of{" "}
              <a className="founder-book" href={BOOK_URL} target="_blank" rel="noopener noreferrer">
                <em>Zero to Forty</em>, available on Amazon
                <ExternalLink size={16} strokeWidth={1.75} aria-hidden="true" />
                <span className="wo-visually-hidden"> (opens in a new tab)</span>
              </a>
              .
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

      <section className="site-band site-band--subtle" aria-labelledby="founder-team">
        <div className="wo-container">
          <div className="wo-page-rule">
            <hr />
            <span className="wo-eyebrow">The team</span>
          </div>
          <h2 className="display-md" id="founder-team" style={{ margin: "var(--space-8) 0 var(--space-4)" }}>
            Community <span className="site-chip">managers</span>
          </h2>
          <p className="founder-team__lead">The people who run WO Community day to day, and the ones to reach out to.</p>
          <ul className="founder-team">
            {TEAM.map((person) => (
              <li key={person.name} className="founder-person">
                <PersonPhoto person={person} />
                <h3 className="founder-person__name">{person.name}</h3>
                <p className="founder-person__role">{person.role}, WO Community</p>
                <a className="founder-person__link" href={person.linkedin} target="_blank" rel="noopener noreferrer">
                  <Linkedin size={16} strokeWidth={1.75} aria-hidden="true" />
                  LinkedIn
                  <span className="wo-visually-hidden"> profile of {person.name} (opens in a new tab)</span>
                </a>
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
