import { useQuery } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { api, unwrap } from "../api/client";
import { Avatar, Button } from "../components";
import { formatDate } from "../lib/format";
import { useToast } from "../ui/Toast";
import "../styles/shared-ui.css";

/** The member's link to share, how many people joined through it, and who they are. No ranking. */
export function ReferralCard() {
  const toast = useToast();
  const mine = useQuery({ queryKey: ["me", "referrals"], queryFn: () => unwrap(api.GET("/api/v1/me/referrals")), staleTime: 60_000 });
  if (!mine.data) return null;
  const { url, approved_count: count, waiting_count: waiting, members } = mine.data;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.show("Link copied");
    } catch {
      toast.show("Select the link and copy it");
    }
  };

  return (
    <div className="wo-refcard">
      <p className="body-sm app-muted" style={{ margin: 0 }}>
        Share this link. When someone you bring in is approved, they are listed here.
      </p>
      <div className="wo-refcard__link">
        <code className="wo-refcard__url" aria-label="Your referral link">
          {url}
        </code>
        <Button variant="secondary" size="sm" icon={<Copy size={16} strokeWidth={1.5} />} onClick={() => void copy()}>
          Copy link
        </Button>
      </div>
      {count > 0 ? (
        <p className="body" style={{ margin: 0 }} role="status">
          {count === 1 ? "1 member joined" : `${count} members joined`} through you.
        </p>
      ) : (
        <p className="body app-muted" style={{ margin: 0 }}>
          Nobody has joined through your link yet.
        </p>
      )}
      {waiting > 0 ? (
        <p className="body-sm app-muted" style={{ margin: 0 }}>
          {waiting === 1 ? "1 person is" : `${waiting} people are`} waiting for approval.
        </p>
      ) : null}
      {members.length > 0 ? (
        <ul className="wo-refcard__list" aria-label="Members who joined through you">
          {members.slice(0, 5).map((m) => (
            <li key={m.id} className="wo-refcard__person">
              <Avatar name={m.name} id={m.id} size="sm" />
              <strong>{m.name}</strong>
              {m.startup ? <span>{m.startup}</span> : null}
              <span>Joined {formatDate(m.joined_at)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
