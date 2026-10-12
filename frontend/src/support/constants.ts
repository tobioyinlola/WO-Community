export const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: "account", label: "Account and sign in" },
  { value: "approval", label: "Approval and membership" },
  { value: "profile", label: "Profile and directory" },
  { value: "learning", label: "Learning and courses" },
  { value: "mentorship", label: "Mentorship" },
  { value: "jobs_events", label: "Jobs and events" },
  { value: "payments", label: "Payments" },
  { value: "problem", label: "Report a problem" },
  { value: "other", label: "Other" },
];

export type TicketTone = "success" | "warning" | "danger" | "neutral" | "info";

/** One tone for each state; the word always comes with it. */
export const STATUS_TONE: Record<string, TicketTone> = {
  open: "neutral",
  in_progress: "info",
  awaiting_member: "warning",
  resolved: "success",
};

/** What the console calls each state. The member's own wording comes from the API. */
export const ADMIN_STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  awaiting_member: "Awaiting member",
  resolved: "Resolved",
};

export const PRIORITIES: Array<{ value: string; label: string }> = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
];

export const SUBJECT_MIN = 5;
export const SUBJECT_MAX = 120;
export const MESSAGE_MIN = 20;
export const MESSAGE_MAX = 4000;
