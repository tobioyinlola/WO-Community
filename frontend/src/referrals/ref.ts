/** The code from a referral link, kept for the visit so it survives moving between pages. */
const KEY = "wo.ref";

export function rememberRefCode(code: string): void {
  try {
    window.sessionStorage.setItem(KEY, code);
  } catch {
    // Storage can be blocked; the code then lives only in the address.
  }
}

export function storedRefCode(): string {
  try {
    return window.sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export const REFERRAL_SOURCES: Array<{ value: string; label: string; detail?: string }> = [
  { value: "member", label: "A WO Community member" },
  { value: "social", label: "Social media", detail: "Which platform? (optional)" },
  { value: "event", label: "An event or demo day", detail: "Which event? (optional)" },
  { value: "partner", label: "A partner organisation", detail: "Which organisation? (optional)" },
  { value: "search", label: "Search engine" },
  { value: "newsletter", label: "Newsletter" },
  { value: "other", label: "Other", detail: "Tell us more (optional)" },
];
