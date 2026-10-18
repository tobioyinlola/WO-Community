import { useAuth } from "../auth/AuthProvider";
import { ShareDialog, type ShareKind } from "../ui/share/ShareDialog";
import { permissionsFor } from "./permissions";

/**
 * The Share dialog from the admin console: posting to the feed is as the team (and can be
 * pinned), offered to admins who may post to the feed; anyone here can share the link.
 */
export function AdminShare({ kind, refId, onClose }: { kind: ShareKind; refId: string; onClose: () => void }) {
  const { me } = useAuth();
  const canPost = permissionsFor(me?.roles ?? []).has("feed.moderate");
  return <ShareDialog kind={kind} refId={refId} onClose={onClose} team feed={canPost} />;
}
