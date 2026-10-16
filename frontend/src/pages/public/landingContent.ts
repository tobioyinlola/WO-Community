import type { FaqItem } from "../../ui/Faq";

/**
 * The words on the landing page that are not tied to the API. Everything here restates what the site
 * already says about itself (the feature cards, the membership section, the sign up and approval
 * flow). Nothing is a made up figure or a made up person.
 */

export const STEPS = [
  { title: "Request access", text: "Tell us what you are building." },
  { title: "Get reviewed", text: "An admin reads every request and replies by email." },
  { title: "Build your profile", text: "Tell your story, with you in control of who sees what." },
  { title: "Meet, learn and launch", text: "Find mentors, take courses and use the launch toolkit." },
] as const;

/** What is hard on your own, and what the community gives instead. The right hand side is the feature copy. */
export const COMPARE = [
  {
    problem: "Finding the right people means asking around and hoping.",
    solution: "A directory of founders, operators and investors across the continent, searchable by what they do and where.",
  },
  {
    problem: "Advice comes from people who have not done what you are doing.",
    solution: "Book a session with a vetted mentor. Real experience, one conversation at a time.",
  },
  {
    problem: "Your plan, numbers and deck live in different places.",
    solution: "Score your idea, write the plan, model the numbers and build the deck, all in one private workspace.",
  },
] as const;

export const FAQ: FaqItem[] = [
  {
    question: "Who can join?",
    answer:
      "Founders, operators and investors who are building in and for Africa, and mentors who have done it before. Admission is by application so the rooms stay useful.",
  },
  {
    question: "What happens after I request access?",
    answer: "An admin reviews your request and replies by email. Until you are approved you see a short holding page instead of the community.",
  },
  {
    question: "Who can see my profile?",
    answer: "Your profile tells your story, and you are in control of who sees what.",
  },
  {
    question: "How do I meet a mentor?",
    answer: "Once you are a member, open Mentors, pick someone who has built what you are building and book a session.",
  },
  {
    question: "Can I post a job?",
    answer: "Yes. Every role on the board comes from someone in the community, and the open roles can be read here on the public site.",
  },
  {
    question: "Where do I get help?",
    answer: "Use Contact support in the footer. It opens the support form.",
  },
];

export interface SocialLink {
  kind: "linkedin" | "x" | "instagram" | "youtube";
  /** The full https address of the community's own page. */
  href: string;
}

/**
 * The community's own social pages. The footer shows a round button for each entry and nothing when
 * the list is empty. Add only addresses that belong to WO Community.
 */
export const SOCIAL_LINKS: SocialLink[] = [];

/**
 * The countries in the strip on the landing page: a fixed list, not taken from member sign ups.
 * Africa first, mixed with the diaspora hubs in North America and Europe.
 */
export const MARQUEE_COUNTRIES = [
  "NG", "GH", "KE", "ZA", "US", "GB", "EG", "RW", "CA", "FR", "ET", "SN", "DE", "NL", "CI", "TZ",
  "IE", "PT", "UG", "MA", "BE", "ES", "CM", "ZW", "IT", "SE", "TN", "BW",
] as const;
