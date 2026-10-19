import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { Badge, Button } from "../../components";
import { EmptyState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../../ui/blocks";
import { useToast } from "../../ui/Toast";
import { Chat, type ChatGroup } from "./groups/Chat";
import "../../styles/groups.css";

const LIST_KEY = ["groups", "list"];

/**
 * Group chats: the community's channels (the WO Men's, Women's and Sport groups, and any the admins
 * add). Join one to read it and talk with the members in it.
 */
export default function Groups() {
  useDocumentTitle("Groups");
  const { groupId } = useParams();
  const navigate = useNavigate();
  const groups = useQuery({
    queryKey: LIST_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/groups")),
    refetchInterval: 15000,
  });
  const open = groups.data?.find((g) => g.id === groupId);

  return (
    <div className={`wo-groups${groupId ? " wo-groups--open" : ""}`}>
      <div className="wo-groups__intro">
        <PageHeader eyebrow="Community" title="Groups" lead="Join a group to chat with the members in it." />
      </div>
      <Loaded
        query={groups}
        skeleton={<SkeletonRows count={3} />}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No groups yet" icon={<MessagesSquare size={24} strokeWidth={1.5} />}>The community team opens groups here.</EmptyState>}
      >
        {(list) => (
          <div className="wo-groups__layout">
            <nav className="wo-groups__list" aria-label="Groups">
              {list.map((g) => (
                <Link
                  key={g.id}
                  to={`/app/groups/${g.id}`}
                  className={`wo-group${g.id === groupId ? " wo-group--current" : ""}`}
                  aria-current={g.id === groupId ? "page" : undefined}
                >
                  <span className="wo-group__emoji" aria-hidden="true">{g.emoji || "💬"}</span>
                  <span className="wo-group__body">
                    <span className="wo-group__name">{g.name}</span>
                    <span className="wo-group__line">
                      {g.joined && g.last_message ? `${g.last_message.author}: ${g.last_message.text}` : g.description || `${g.member_count} members`}
                    </span>
                  </span>
                  {g.unread ? <span className="wo-group__unread" aria-label={`${g.unread} unread`}>{g.unread >= 99 ? "99+" : g.unread}</span> : null}
                  {!g.joined ? <Badge variant="neutral">Join</Badge> : null}
                </Link>
              ))}
            </nav>
            <div className="wo-groups__pane">
              {open ? (
                open.joined ? (
                  <Chat key={open.id} group={open} onBack={() => navigate("/app/groups")} />
                ) : (
                  <Preview group={open} onBack={() => navigate("/app/groups")} />
                )
              ) : groupId ? (
                <EmptyState title="We could not find that group">It may have been closed. Choose another group.</EmptyState>
              ) : (
                <div className="wo-groups__pick">
                  <MessagesSquare size={40} strokeWidth={1.25} aria-hidden="true" />
                  <p>Choose a group to start chatting.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </Loaded>
    </div>
  );
}

function Preview({ group, onBack }: { group: ChatGroup; onBack: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const join = async () => {
    setBusy(true);
    try {
      await unwrap(api.POST("/api/v1/groups/{group_id}/membership", { params: { path: { group_id: group.id } } }));
      await client.invalidateQueries({ queryKey: LIST_KEY });
      toast.show(`Welcome to ${group.name}`);
    } catch (e) {
      toast.show(messageOf(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="wo-groups__preview" aria-labelledby="group-preview">
      <button type="button" className="wo-chat__icon wo-chat__back" onClick={onBack} aria-label="All groups">←</button>
      <span className="wo-groups__bigemoji" aria-hidden="true">{group.emoji || "💬"}</span>
      <h2 id="group-preview" className="h3">{group.name}</h2>
      {group.description ? <p>{group.description}</p> : null}
      <p className="caption app-muted"><Users size={14} strokeWidth={1.75} aria-hidden="true" /> {group.member_count} {group.member_count === 1 ? "member" : "members"}</p>
      <Button loading={busy} onClick={() => void join()}>Join group</Button>
      <p className="caption app-muted">Be kind and keep to the <Link className="app-link" to="/legal/conduct">Code of Conduct</Link>.</p>
    </section>
  );
}
