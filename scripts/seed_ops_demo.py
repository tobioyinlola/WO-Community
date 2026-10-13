# ruff: noqa: E501, E402, S311
"""Add job applications and mentoring sessions to the demo community, so the admin pages have
something to show. Run after seed_demo.py and seed_rich_demo.py. Local only; safe to run again.

    python manage.py shell -c "exec(open('scripts/seed_ops_demo.py', encoding='utf8').read())"
"""

import random
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from psycopg.types.range import Range

from apps.accounts.models import User
from apps.jobs import selectors as job_selectors
from apps.jobs.models import JobApplication
from apps.mentorship.models import ACTIVE_SESSION_STATUSES, MentorProfile, MentorSession

random.seed(11)
now = timezone.now()

NOTES = [
    "I have spent four years building payments products in Lagos and would love to help you ship faster.",
    "Your mission matches what I care about. I have led a small team before and enjoy the early, messy stage.",
    "I run a community of 2,000 founders and know how to grow a product from nothing. Happy to share results.",
    "I am finishing a degree in computer science and have shipped two apps used by real customers.",
    "Operations is my strength: I cut onboarding time in half at my last company. I would like to do the same for you.",
]
STATUSES = ["submitted", "submitted", "reviewing", "shortlisted", "rejected", "hired"]

members = list(
    User.objects.filter(status="active", email__endswith="@demo.test").exclude(
        email__startswith="admin"
    )
)
jobs = list(job_selectors.live_jobs()[:8])
made = 0
for job in jobs:
    for member in random.sample(members, k=min(len(members), random.randint(1, 3))):
        if member.pk == job.poster_id:
            continue
        _, created = JobApplication.objects.get_or_create(
            job=job,
            applicant=member,
            defaults={
                "note": random.choice(NOTES),
                "link": f"https://cv.example/{member.email.split('@')[0]}",
                "status": random.choice(STATUSES),
            },
        )
        made += created
print(f"job applications added: {made}, total {JobApplication.objects.count()}")

mentors = list(MentorProfile.objects.filter(status="active").select_related("user"))
print(f"mentors found: {len(mentors)}")


def clashes(mentor_id, mentee, status, start, end):
    """Whether the database would refuse this session, checked first so nothing is caught later.

    It refuses a mentor or a founder in two live sessions at overlapping times, and a second
    waiting request from the same founder to the same mentor. Closed sessions never clash.
    """
    if status not in ACTIVE_SESSION_STATUSES:
        return False
    live = MentorSession.objects.filter(status__in=ACTIVE_SESSION_STATUSES)
    overlapping = live.filter(starts_at__lt=end, ends_at__gt=start)
    if overlapping.filter(Q(mentor_id=mentor_id) | Q(mentee=mentee)).exists():
        return True
    return (
        status == "requested"
        and live.filter(status="requested", mentor_id=mentor_id, mentee=mentee).exists()
    )


sessions = 0
already = 0
clashed = 0
topics = [
    "Fundraising strategy",
    "First ten customers",
    "Hiring a CTO",
    "Pricing your product",
    "Pitch deck review",
    "Going to market in Ghana",
]
statuses = [
    "completed",
    "completed",
    "confirmed",
    "confirmed",
    "requested",
    "cancelled",
    "declined",
]
for i, mentor in enumerate(mentors[:5]):
    for j in range(2):
        mentee = members[(i * 2 + j) % len(members)]
        if mentee.pk == mentor.user_id:
            continue
        status = statuses[(i + j) % len(statuses)]
        closed = status in ("completed", "cancelled", "declined")
        offset = timedelta(days=-(3 + i + j) if closed else 2 + i + j)
        start = (now + offset).replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=45)
        if MentorSession.objects.filter(
            mentor_id=mentor.user_id, mentee=mentee, starts_at=start
        ).exists():
            already += 1
            continue
        if clashes(mentor.user_id, mentee, status, start, end):
            clashed += 1
            continue
        MentorSession.objects.create(
            mentor_id=mentor.user_id,
            mentee=mentee,
            starts_at=start,
            ends_at=end,
            time_span=Range(start, end),
            topic=topics[(i + j) % len(topics)],
            message="I would value your honest view on where to focus next.",
            status=status,
            length_minutes=45,
            confirmed_at=now if status in ("confirmed", "completed") else None,
            completed_at=start if status == "completed" else None,
            closed_reason="Schedule clash" if status in ("cancelled", "declined") else "",
        )
        sessions += 1
print(
    f"mentoring sessions: {sessions} added, {already} already there, "
    f"{clashed} left out because the time would overlap; total {MentorSession.objects.count()}"
)
