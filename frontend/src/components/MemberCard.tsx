import { Avatar, type AvatarTint } from "./Avatar";
import { Badge, type BadgeVariant } from "./Badge";
import { Button } from "./Button";
import { cx } from "../lib/cx";

/** The four fixed role words, and the badge each always uses. */
export type MemberRole = "founder" | "operator" | "investor" | "mentor";

const ROLE_LABEL: Record<MemberRole, string> = {
  founder: "Founder",
  operator: "Operator",
  investor: "Investor",
  mentor: "Mentor",
};
const ROLE_BADGE: Record<MemberRole, BadgeVariant> = {
  founder: "founder",
  operator: "operator",
  investor: "investor",
  mentor: "mentor",
};

export interface MemberCardProps {
  id: string;
  name: string;
  /** Only fields the viewer is allowed to see; leave out the rest and nothing renders for them. */
  title?: string;
  company?: string;
  location?: string;
  roles?: MemberRole[];
  photoUrl?: string;
  tint?: AvatarTint;
  mutualConnections?: number;
  onConnect?: (id: string) => void;
  className?: string;
}

/** One member in the directory: scannable in two seconds. At most three role badges. */
export function MemberCard({
  id,
  name,
  title,
  company,
  location,
  roles = [],
  photoUrl,
  tint,
  mutualConnections,
  onConnect,
  className,
}: MemberCardProps) {
  const position = [title, company].filter(Boolean).join(", ");
  return (
    <article className={cx("wo-card wo-member", className)} aria-label={name}>
      <div className="wo-member__head">
        <Avatar id={id} name={name} src={photoUrl} tint={tint} shape="arch" size="lg" />
        <div>
          <h3 className="wo-member__name">{name}</h3>
          {position ? <p className="wo-member__meta">{position}</p> : null}
          {location ? <p className="wo-member__meta">{location}</p> : null}
        </div>
      </div>
      {roles.length > 0 ? (
        <div className="wo-member__tags">
          {roles.slice(0, 3).map((role) => (
            <Badge key={role} variant={ROLE_BADGE[role]}>
              {ROLE_LABEL[role]}
            </Badge>
          ))}
        </div>
      ) : null}
      <div className="wo-member__foot">
        {mutualConnections !== undefined ? (
          <span className="wo-hint">{mutualConnections} mutual</span>
        ) : (
          <span />
        )}
        {onConnect ? (
          <Button variant="secondary" size="sm" onClick={() => onConnect(id)}>
            Connect
          </Button>
        ) : null}
      </div>
    </article>
  );
}
