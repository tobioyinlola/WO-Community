import { MessageCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Button, Modal } from "../components";

/** Set once the invitation has been shown in this tab; cleared on sign-out so the next sign-in shows it. */
export const INVITE_SEEN_KEY = "wo-community-invite-seen";

function seenThisSignIn(): boolean {
  try {
    return sessionStorage.getItem(INVITE_SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Asks a member to join the WhatsApp community when they sign in. The server decides whether it is
 * still due (three showings, or never again once the link was followed), so this only has to show
 * it once per sign-in and tell the server when it did.
 */
export function CommunityInvite() {
  const { me } = useAuth();
  const url = me?.community_invite_url ?? null;
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!url || seenThisSignIn()) return;
    try {
      sessionStorage.setItem(INVITE_SEEN_KEY, "1");
    } catch {
      // Private mode: the server still stops it after three showings.
    }
    setOpen(true);
    void api.POST("/api/v1/me/community-invite/shown");
  }, [url]);

  if (!url) return null;
  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      eyebrow="WO Community"
      title="Join our WhatsApp community"
      actions={
        <>
          <Button variant="ghost" onClick={() => setOpen(false)}>Maybe later</Button>
          <a
            className="wo-invite__join"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => {
              void api.POST("/api/v1/me/community-invite/joined");
              setOpen(false);
            }}
          >
            <MessageCircle size={18} aria-hidden="true" /> Join on WhatsApp
          </a>
        </>
      }
    >
      <p>
        Members chat on WhatsApp every day: sharing wins, asking for advice and helping each other out.
        If you have not joined yet, come and say hello.
      </p>
    </Modal>
  );
}
