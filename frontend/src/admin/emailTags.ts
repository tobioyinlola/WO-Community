/** Turning typed or pasted text into email addresses for the invitation field. */

export const MAX_EMAILS = 200;

// Deliberately plain: one @, something either side, a dot in the domain. The server checks again.
const SHAPE = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]{2,}$/;

export type Flag = "invalid" | "member" | "pending";

export interface Chip {
  email: string;
  /** Set by the browser's own check, or by the server's check of who is already here. */
  flag?: Flag;
}

/** Pieces of a pasted or typed list, split on commas, semicolons, spaces and new lines. */
export function splitList(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((piece) => piece.replace(/^<|>$/g, "").trim())
    .filter(Boolean);
}

export function isValidShape(email: string): boolean {
  return email.length <= 254 && SHAPE.test(email);
}

export const FLAG_TEXT: Record<Flag, string> = {
  invalid: "Not a valid email address",
  member: "Already a member",
  pending: "Invite pending",
};

/**
 * Add the pieces to a list of chips. Addresses already there are merged (compared without regard to
 * capital letters), the total stops at the limit, and the numbers dropped are returned.
 */
export function addChips(current: Chip[], pieces: string[]): { chips: Chip[]; merged: number; overflow: number } {
  const seen = new Set(current.map((c) => c.email.toLowerCase()));
  const chips = [...current];
  let merged = 0;
  let overflow = 0;
  for (const piece of pieces) {
    const key = piece.toLowerCase();
    if (seen.has(key)) {
      merged += 1;
    } else if (chips.length >= MAX_EMAILS) {
      overflow += 1;
    } else {
      seen.add(key);
      chips.push(isValidShape(piece) ? { email: piece } : { email: piece, flag: "invalid" });
    }
  }
  return { chips, merged, overflow };
}

/** The addresses that will be sent: valid, and not already a member or invited. */
export function sendable(chips: Chip[]): string[] {
  return chips.filter((c) => !c.flag).map((c) => c.email);
}
