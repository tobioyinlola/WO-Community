import type { LucideIcon } from "lucide-react";
import { useState } from "react";

/**
 * A topic's picture, or until one is supplied a forest and sand gradient with the topic's icon.
 * Each use is listed in docs/changes/landing-media-needed.md. A picture keeps the dark overlay, so
 * text on top stays readable, and a picture that fails to load falls back to the gradient.
 */
export function MediaPlaceholder({ icon: Icon, src, alt = "" }: { icon: LucideIcon; src?: string; alt?: string }) {
  const [failed, setFailed] = useState(false);
  const shown = src && !failed;
  return (
    <div className="wo-media" data-placeholder={shown ? undefined : "true"}>
      {shown ? (
        <img src={src} alt={alt} loading="lazy" decoding="async" width={640} height={400} onError={() => setFailed(true)} />
      ) : (
        <Icon size={64} strokeWidth={1} aria-hidden="true" />
      )}
    </div>
  );
}
