"""What a support request can be about and where it stands. Plain data, no framework."""

CATEGORY_LABELS = {
    "account": "Account and sign in",
    "approval": "Approval and membership",
    "profile": "Profile and directory",
    "learning": "Learning and courses",
    "mentorship": "Mentorship",
    "jobs_events": "Jobs and events",
    "payments": "Payments",
    "problem": "Report a problem",
    "other": "Other",
}
CATEGORIES = tuple(CATEGORY_LABELS)

STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "awaiting_member": "Awaiting your reply",
    "resolved": "Resolved",
}
STATUSES = tuple(STATUS_LABELS)
OPEN_STATUSES = ("open", "in_progress", "awaiting_member")

PRIORITIES = ("low", "normal", "high")

AUTHOR_TYPES = ("member", "admin", "system")

SUBJECT_MIN, SUBJECT_MAX = 5, 120
FIRST_MESSAGE_MIN, MESSAGE_MAX = 20, 4000
MAX_ATTACHMENTS = 3
ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024

# A member can reopen a resolved request for this long after it was resolved.
REOPEN_DAYS = 14

SATISFACTION = ("up", "down")
