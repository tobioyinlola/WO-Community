"""Warming up a new sending domain: a cap on how many newsletters go out per hour.

Mailbox providers trust a new domain slowly. Sending a whole audience on day one looks like spam,
so until the domain has a history the number of broadcast emails per hour is held down and raised
step by step. Transactional mail (verification, approvals, password resets) is never limited.

Set ``EMAIL_WARMUP_START`` (a date, YYYY-MM-DD) to follow the schedule below, or set
``EMAIL_HOURLY_CAP`` to a fixed number (0 means no limit, -1 means follow the schedule).
"""

from datetime import date

from django.conf import settings

# (day of warm up from which it applies, broadcast emails per hour)
SCHEDULE: tuple[tuple[int, int], ...] = (
    (1, 50),
    (3, 100),
    (5, 250),
    (8, 500),
    (11, 1000),
    (15, 2500),
    (22, 5000),
    (29, 10000),
)


def hourly_cap(today: date) -> int | None:
    """The most broadcast emails to send in an hour today, or None when there is no limit."""
    fixed = int(settings.EMAIL_HOURLY_CAP)
    if fixed > 0:
        return fixed
    if fixed == 0:
        return None
    start = settings.EMAIL_WARMUP_START
    if not start:
        return None
    day = (today - date.fromisoformat(start)).days + 1
    if day < 1:
        return SCHEDULE[0][1]
    cap: int | None = None
    for from_day, per_hour in SCHEDULE:
        if day >= from_day:
            cap = per_hour
    return cap if day < SCHEDULE[-1][0] + 14 else None  # two weeks after the last step: done


def room(today: date, sent_last_hour: int) -> int | None:
    """How many more may go out now: None for no limit, otherwise zero or more."""
    cap = hourly_cap(today)
    if cap is None:
        return None
    return max(0, cap - sent_last_hour)
