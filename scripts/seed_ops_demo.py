# ruff: noqa: E501, E402, S311
"""Add job applications and mentoring sessions to the demo community, so the admin pages have
something to show. Run after seed_demo.py and seed_rich_demo.py. Local only; safe to run again.

    python manage.py shell -c "exec(open('scripts/seed_ops_demo.py', encoding='utf8').read())"
"""

import random
from datetime import timedelta

from django.utils import timezone
from psycopg.types.range import Range

from apps.accounts.models import User
from apps.jobs import selectors as job_selectors
from apps.jobs.models import JobApplication
from apps.mentorship.models import MentorProfile, MentorSession

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

members = list(User.objects.filter(status="active", email__endswith="@demo.test").exclude(email__startswith="admin"))
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

mentors = list(MentorProfile.objects.filter(status="active").select_related("user")) if hasattr(MentorProfile, "status") else list(MentorProfile.objects.all()[:6])
print(f"mentors found: {len(mentors)}")
sessions = 0
topics = ["Fundraising strategy", "First ten customers", "Hiring a CTO", "Pricing your product", "Pitch deck review", "Going to market in Ghana"]
statuses = ["completed", "completed", "confirmed", "confirmed", "requested", "cancelled", "declined"]
for i, mentor in enumerate(mentors[:5]):
    for j in range(2):
        mentee = members[(i * 2 + j) % len(members)]
        if mentee.pk == mentor.user_id:
            continue
        status = statuses[(i + j) % len(statuses)]
        offset = timedelta(days=-(3 + i + j) if status in ("completed", "cancelled", "declined") else 2 + i + j)
        start = (now + offset).replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=45)
        if MentorSession.objects.filter(mentor_id=mentor.user_id, mentee=mentee, starts_at=start).exists():
            continue
        try:
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
        except Exception as exc:  # an overlap with an existing session is fine to skip
            print("skipped a session:", str(exc)[:80])
print(f"mentoring sessions added: {sessions}, total {MentorSession.objects.count()}")
