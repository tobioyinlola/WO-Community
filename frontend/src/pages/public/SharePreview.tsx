import { useQuery } from "@tanstack/react-query";
import { BookOpen, CalendarDays, Lock, MessageSquareQuote } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { ArrowCircle } from "../../ui/ArrowCircle";
import { SkeletonRows, useDocumentTitle } from "../../ui/blocks";

const ICONS = { course: BookOpen, event: CalendarDays, post: MessageSquareQuote } as const;

/** What a member gets that the brief leaves out, by kind. */
type Rest = { what: string; perks: string[] };
const REST: Record<"course" | "event" | "post", Rest> = {
  course: {
    what: "The full course is for members",
    perks: ["Every lecture, reading and resource", "Track your progress and earn a certificate", "Ask questions and learn with other founders"],
  },
  event: {
    what: "The full event is for members",
    perks: ["The details and how to join", "Register and get reminders", "Meet the founders and operators going"],
  },
  post: {
    what: "The full post is for members",
    perks: ["Read it all and see who is talking", "React, comment and join the conversation", "Follow the founders building across Africa"],
  },
};

/**
 * Where a link shared outside the platform lands: the brief of a course, event or post, and an
 * invitation to become a member (or sign in) to see the rest. Members go straight to it.
 */
export default function SharePreview() {
  const { kind = "", ref = "" } = useParams();
  const { status } = useAuth();
  const card = useQuery({
    queryKey: ["share-card", kind, ref],
    queryFn: () => unwrap(api.GET("/api/v1/public/share/{kind}/{ref}", { params: { path: { kind, ref } } })),
    retry: false,
  });
  useDocumentTitle(card.data?.title ?? "Shared with you");

  if (status === "authenticated" && card.data) return <Navigate to={card.data.url} replace />;
  const rest: Rest = REST[kind as keyof typeof REST] ?? REST.post;
  const Icon = ICONS[kind as keyof typeof ICONS] ?? BookOpen;

  return (
    <section className="site-band" aria-labelledby="share-title">
      <div className="wo-container wo-container--narrow">
        {card.isPending || status === "loading" ? <SkeletonRows /> : null}
        {card.isError ? (
          <div className="wo-teaser wo-teaser--gone">
            <h1 className="h2" id="share-title" style={{ margin: 0 }}>This link is no longer shared</h1>
            <p className="body app-muted" style={{ margin: 0 }}>It may have ended or been taken down. There is plenty more inside WO Community.</p>
            <div className="app-cluster" style={{ justifyContent: "center" }}>
              <Link className="wo-btn wo-btn--accent" to="/register">Become a member <ArrowCircle /></Link>
              <Link className="wo-btn wo-btn--secondary" to="/explore">Explore the community</Link>
            </div>
          </div>
        ) : null}
        {card.data ? (
          <article className="wo-teaser">
            <div className="wo-teaser__media" aria-hidden="true">
              {card.data.image ? <img src={card.data.image} alt="" /> : <Icon size={56} strokeWidth={1.1} />}
            </div>
            <div className="wo-teaser__body">
              <p className="wo-teaser__badge">{card.data.badge}</p>
              <h1 className="wo-teaser__title" id="share-title">{card.data.title}</h1>
              {card.data.facts.length || card.data.by ? (
                <p className="wo-teaser__facts">{[card.data.kind === "course" && card.data.by ? `Taught by ${card.data.by}` : "", ...card.data.facts].filter(Boolean).join(" · ")}</p>
              ) : null}
              {card.data.excerpt ? <p className="wo-teaser__excerpt">{card.data.excerpt}</p> : null}
              <div className="wo-teaser__locked" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <div className="wo-teaser__gate">
                <p className="wo-teaser__gate-title">
                  <Lock size={18} strokeWidth={1.75} aria-hidden="true" /> {rest.what}
                </p>
                <ul className="wo-teaser__perks">
                  {rest.perks.map((perk) => <li key={perk}>{perk}</li>)}
                </ul>
                <div className="app-cluster">
                  <Link className="wo-btn wo-btn--accent wo-btn--lg" to="/register">
                    Become a member <ArrowCircle />
                  </Link>
                  <Link className="wo-btn wo-btn--secondary wo-btn--lg" to="/login" state={{ from: card.data.url }}>
                    Sign in
                  </Link>
                </div>
                <p className="caption app-muted" style={{ margin: 0 }}>
                  Already a member? Sign in and it opens straight away.
                </p>
              </div>
            </div>
          </article>
        ) : null}
      </div>
    </section>
  );
}
