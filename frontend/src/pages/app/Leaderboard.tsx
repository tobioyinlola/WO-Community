import { useQuery } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Avatar, Card, StatTile } from "../../components";
import { EmptyState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../../ui/blocks";

type Board = components["schemas"]["Leaderboard"];
type Points = components["schemas"]["Points"];

export function useLeaderboard() {
  return useQuery({
    queryKey: ["leaderboard"],
    queryFn: () => unwrap(api.GET("/api/v1/leaderboard")),
    staleTime: 60_000,
  });
}

const EARNED: Array<[keyof Points, string, string]> = [
  ["posts", "Post in the feed", "post"],
  ["comments", "Comment on a post", "comment"],
  ["news_comments", "Comment on a news story", "news comment"],
  ["reactions_given", "React to a post, comment or story", "reaction"],
  ["reactions_received", "Get a reaction on your post", "reaction received"],
  ["login_days", "Sign in, once a day", "day signed in"],
];

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** What earned the points, in words: "2 posts, 5 reactions". */
function earnedFrom(breakdown: Points) {
  return EARNED.filter(([key]) => breakdown[key] > 0)
    .map(([key, , word]) => plural(breakdown[key], word))
    .join(", ");
}

/** The ranked list, for the dashboard and the full page. */
export function LeaderList({ board, compact = false }: { board: Board; compact?: boolean }) {
  if (board.entries.length === 0) {
    return (
      <EmptyState title="Nobody has points yet">
        Post, comment and react in the community to be the first on the board.
      </EmptyState>
    );
  }
  return (
    <ol className="wo-leaders" aria-label={`Top ${board.entries.length} members`}>
      {board.entries.map((entry) => (
        <li key={entry.user_id} className="wo-leaders__row" data-me={entry.is_me || undefined} data-top={entry.rank <= 3 || undefined}>
          <span className="wo-leaders__rank" aria-label={`Rank ${entry.rank}`}>
            {entry.rank}
          </span>
          <Avatar name={entry.name} id={entry.user_id} src={entry.photo?.thumb} size="sm" />
          <span className="wo-leaders__who">
            <Link className="wo-leaders__name" to={`/app/members/${entry.user_id}`}>
              {entry.name}
              {entry.is_me ? <span className="wo-leaders__you"> (you)</span> : null}
            </Link>
            {!compact ? <span className="wo-leaders__how">{earnedFrom(entry.breakdown)}</span> : null}
          </span>
          <span className="wo-leaders__points">
            {entry.points}
            <span className="wo-leaders__unit"> pts</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export default function Leaderboard() {
  useDocumentTitle("Leaderboard");
  const board = useLeaderboard();
  return (
    <>
      <PageHeader
        eyebrow="Community"
        title="Leaderboard"
        lead="The ten most engaged members over the last 30 days. Everyone who takes part earns points."
      />
      <Loaded query={board} skeleton={<SkeletonRows />}>
        {(data) => (
          <div className="app-split">
            <div className="app-stack app-stack--lg">
              <Card>
                <LeaderList board={data} />
              </Card>
            </div>
            <div className="app-stack app-stack--lg">
              <StatTile
                variant="brand"
                label="Your rank"
                value={data.me.rank ? `#${data.me.rank}` : "Not ranked yet"}
                delta={
                  data.me.rank
                    ? `${data.me.points} points, of ${data.me.ranked_members} members with points`
                    : "Take part to earn your first points"
                }
              />
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)", display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                  <Trophy size={18} strokeWidth={1.75} aria-hidden="true" /> How points work
                </h2>
                <ul className="wo-points">
                  {EARNED.map(([key, label]) => (
                    <li key={key}>
                      <span>{label}</span>
                      <strong>+{data.points[key]}</strong>
                    </li>
                  ))}
                </ul>
                <p className="body-sm app-muted" style={{ margin: "var(--space-3) 0 0" }}>
                  Counted over the last {data.period_days} days and updated every few minutes. Hidden or removed posts
                  don&rsquo;t count, and nor do reactions to your own posts.
                </p>
              </Card>
            </div>
          </div>
        )}
      </Loaded>
    </>
  );
}
