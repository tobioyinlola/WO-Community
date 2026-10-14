import type { LucideIcon } from "lucide-react";

/**
 * Stands in for a photo that has not been supplied yet: a forest and sand gradient with the topic's
 * icon. Each use is listed in docs/changes/landing-media-needed.md. A real picture goes in the same
 * box and keeps the dark overlay, so text on top stays readable.
 */
export function MediaPlaceholder({ icon: Icon, src, alt = "" }: { icon: LucideIcon; src?: string; alt?: string }) {
  return (
    <div className="wo-media" data-placeholder={src ? undefined : "true"}>
      {src ? <img src={src} alt={alt} loading="lazy" width={640} height={400} /> : <Icon size={64} strokeWidth={1} aria-hidden="true" />}
    </div>
  );
}
