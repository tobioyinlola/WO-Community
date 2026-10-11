import { cx } from "../lib/cx";

export type AvatarShape = "arch" | "capsule" | "bloom" | "circle";
export type AvatarSize = "sm" | "md" | "lg" | "xl";
export type AvatarTint = "peach" | "amber" | "mint" | "periwinkle" | "lilac";

const TINTS: AvatarTint[] = ["peach", "amber", "mint", "periwinkle", "lilac"];

/** A tint that never changes for the same id, so a member keeps their colour everywhere. */
export function tintFor(id: string): AvatarTint {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TINTS[hash % TINTS.length] ?? "amber";
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  const first = words[0] ?? "";
  const last = words.length > 1 ? (words[words.length - 1] ?? "") : "";
  return (first.charAt(0) + last.charAt(0)).toUpperCase();
}

export interface AvatarProps {
  name: string;
  /** Stable member id, used to choose the tint when none is given. */
  id?: string;
  src?: string;
  shape?: AvatarShape;
  size?: AvatarSize;
  tint?: AvatarTint;
  className?: string;
}

/** A member's photo, or their initials on a tint, in the brand's arch, capsule or bloom frame. */
export function Avatar({
  name,
  id,
  src,
  shape = "circle",
  size = "md",
  tint,
  className,
}: AvatarProps) {
  const chosen = tint ?? tintFor(id ?? name);
  return (
    <span
      role="img"
      aria-label={name}
      className={cx(
        "wo-avatar",
        shape !== "circle" && `wo-avatar--${shape}`,
        size !== "md" && `wo-avatar--${size}`,
        `wo-avatar--${chosen}`,
        className,
      )}
    >
      {src ? <img src={src} alt="" /> : <span aria-hidden="true">{initials(name)}</span>}
    </span>
  );
}
