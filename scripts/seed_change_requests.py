"""Adds the data the newer screens need on top of the demo community.

Run from the repository root with the local settings, after `seed_demo.py`:

    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_change_requests.py

`seed_demo.py` calls this at the end, so a fresh database gets it too. Every step checks what is
there first, so the script is safe to run again. Everything is made up, and it refuses to run
outside local settings.

What it adds: a referral chain, three more courses (one free, one paid with a promotion, one draft),
a request for the paid course, support requests in each status, notifications for the demo member,
mentor pricing, and a revoked certificate beside the live ones.
"""

import contextlib
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

if not settings.DEBUG:
    sys.exit("Refusing to seed demo data outside local development.")

from apps.accounts import referrals  # noqa: E402
from apps.accounts.models import User  # noqa: E402
from apps.learning import authoring as learning  # noqa: E402
from apps.learning import certificates, engage, learn, lms  # noqa: E402
from apps.learning.models import Certificate, Course, Enrolment, Lesson  # noqa: E402
from apps.mentorship import setup as mentor_setup  # noqa: E402
from apps.mentorship.models import MentorProfile  # noqa: E402
from apps.notifications import notify  # noqa: E402
from apps.support import services as support  # noqa: E402
from apps.support.models import SupportTicket  # noqa: E402

# who heard of us how: email, how, who or what
REFERRALS = [
    ("tunde@demo.test", "member", "amaka@demo.test", ""),
    ("ngozi@demo.test", "member", "amaka@demo.test", ""),
    ("jide@demo.test", "member", "tunde@demo.test", ""),
    ("zanele@demo.test", "member", "tunde@demo.test", ""),
    ("chidi@demo.test", "member", "ngozi@demo.test", ""),
    ("funmi@demo.test", "social", "", "LinkedIn"),
    ("kwame@demo.test", "event", "", "Demo Day, Accra"),
    ("aisha@demo.test", "partner", "", "A university incubator"),
    ("samuel@demo.test", "other", "", "A friend told me at a conference"),
]

COURSES = [
    {
        "title": "Customer discovery for founders",
        "subtitle": "Talk to the right people and learn what to build.",
        "category": "Foundations",
        "level": "beginner",
        "access": "free",
        "open_to_visitors": True,
        "learn_bullets": [
            "Plan interviews",
            "Ask questions that get honest answers",
            "Spot patterns",
        ],
        "requirements": ["No experience needed"],
        "publish": True,
    },
    {
        "title": "Financial models investors trust",
        "subtitle": "Build a forecast you can defend in the room.",
        "category": "Funding",
        "level": "advanced",
        "access": "paid",
        "price_minor": 2_500_000,
        "currency": "NGN",
        "open_to_visitors": False,
        "learn_bullets": [
            "Structure revenue and costs",
            "Model runway",
            "Explain your assumptions",
        ],
        "requirements": ["A spreadsheet tool", "Basic accounting terms"],
        "promo": True,
        "publish": True,
    },
    {
        "title": "Hiring your first ten people",
        "subtitle": "In preparation.",
        "category": "Team",
        "level": "intermediate",
        "access": "free",
        "open_to_visitors": False,
        "publish": False,
    },
]

TICKETS = [
    # who, category, subject, message, final state
    (
        "amaka@demo.test",
        "learning",
        "I cannot see my certificate",
        "I finished the fundraising course last week but the certificate does not show on my page.",
        "open",
    ),
    (
        "tunde@demo.test",
        "mentorship",
        "How do I change a booked session?",
        "I booked a session with a mentor for Thursday and need to move it to the following week.",
        "in_progress",
    ),
    (
        "ngozi@demo.test",
        "account",
        "Update the email on my account",
        "My work email changed and I would like to sign in with the new address from now on.",
        "awaiting_member",
    ),
    (
        "jide@demo.test",
        "profile",
        "My startup is not in the directory",
        "I turned on the directory setting two days ago, but my startup is still not in the list.",
        "resolved",
    ),
]


def person(email: str) -> User:
    return User.objects.get(email=email)


def seed_referrals() -> None:
    for email, kind, who, detail in REFERRALS:
        user = person(email)
        if user.referral_source:
            continue
        data: dict = {"kind": kind, "detail": detail}
        if who:
            data["referred_by"] = person(who).pk
        referrals.capture(user, data)
    for user in User.objects.filter(email__endswith="@demo.test", referral_code__isnull=True):
        referrals.ensure_code(user)


def seed_courses(admin: User) -> None:
    for spec in COURSES:
        if Course.objects.filter(title=spec["title"]).exists():
            continue
        data = {
            "title": spec["title"],
            "description": f"<p>{spec['title']}. {spec['subtitle']}</p>",
            "instructor": "WO Community faculty",
            "category": spec["category"],
            "level": spec["level"],
            "access": spec["access"],
            "open_to_visitors": spec["open_to_visitors"],
            "certificate_enabled": True,
            "subtitle": spec["subtitle"],
            "language": "en",
            "learn_bullets": spec.get("learn_bullets", []),
            "requirements": spec.get("requirements", []),
            "audience": "Founders and early team members.",
        }
        if spec["access"] == "paid":
            data["price_minor"] = spec["price_minor"]
            data["currency"] = spec["currency"]
        if spec.get("promo"):
            now = timezone.now()
            data["promo_price_minor"] = int(spec["price_minor"] * 0.8)
            data["promo_starts_at"] = now - timedelta(days=1)
            data["promo_ends_at"] = now + timedelta(days=20)
        course = learning.create_course(actor=admin, data=data)
        for title, lessons in (("Foundations", 3), ("Putting it to work", 2)):
            module = learning.add_module(actor=admin, course_id=course.pk, title=title)
            for n in range(1, lessons + 1):
                learning.add_lesson(
                    actor=admin,
                    module_id=module.pk,
                    data={
                        "type": "reading",
                        "title": f"{title}, part {n}",
                        "duration_seconds": 240 * n,
                        "body": f"<p>{title}, part {n}. Lesson text for {spec['title']}.</p>",
                    },
                )
        if spec["publish"]:
            Course.objects.filter(pk=course.pk).update(
                status="published", published_at=timezone.now()
            )
        lms.refresh_counts(course.pk)

    paid = Course.objects.filter(title="Financial models investors trust").first()
    if paid is not None:
        with contextlib.suppress(Exception):  # already asked, or already enrolled
            engage.request_access(
                user_id=person("tunde@demo.test").pk,
                course_id=paid.pk,
                message="I am preparing a seed round and would like to build the model properly.",
            )
    free = Course.objects.filter(title="Customer discovery for founders").first()
    if free is not None:
        for email, finished in (("ngozi@demo.test", False), ("jide@demo.test", True)):
            user = person(email)
            if Enrolment.objects.filter(user=user, course=free).exists():
                continue
            learn.enrol(user_id=user.pk, course_id=free.pk)
            lessons = Lesson.objects.filter(course=free).order_by("module__position", "position")
            for lesson in lessons if finished else lessons[:2]:
                learn.update_progress(
                    user_id=user.pk, lesson_id=lesson.pk, position_seconds=None, completed=True
                )
            if finished:
                certificates.issue(Enrolment.objects.get(user=user, course=free).pk)

    # One certificate that has been withdrawn, so the admin list and the verification page show it.
    withdrawn = Certificate.objects.filter(
        enrolment__user__email="jide@demo.test", revoked_at__isnull=True
    ).first()
    if withdrawn is not None and not Certificate.objects.filter(revoked_at__isnull=False).exists():
        certificates.revoke(
            actor=admin,
            certificate_id=withdrawn.pk,
            reason="Issued by mistake; the course was not finished.",
        )


def seed_tickets(admin: User) -> None:
    if SupportTicket.objects.exists():
        return
    for email, category, subject, message, state in TICKETS:
        member = person(email)
        ticket = support.create_ticket(
            member=member,
            name="",
            email=member.email,
            category=category,
            subject=subject,
            message=message,
        )
        if state == "open":
            continue
        support.update_ticket(
            ticket_id=ticket.pk, admin=admin, changes={"assignee": admin.pk, "priority": "high"}
        )
        if state == "in_progress":
            support.update_ticket(
                ticket_id=ticket.pk, admin=admin, changes={"status": "in_progress"}
            )
            continue
        support.add_admin_message(
            ticket_id=ticket.pk,
            admin=admin,
            body="Thank you for writing. Could you tell us which address you would like to use?",
            status="awaiting_member" if state == "awaiting_member" else "in_progress",
        )
        if state == "resolved":
            support.add_admin_message(
                ticket_id=ticket.pk,
                admin=admin,
                body="Your startup is listed now. It can take a few minutes to appear.",
                status="resolved",
            )


def seed_notifications() -> None:
    amaka = person("amaka@demo.test")
    if amaka.notifications.filter(type="course_announcement").exists():
        return
    course = Course.objects.filter(title="Fundraising for African startups").first()
    if course is not None:
        notify.notify(
            amaka.pk,
            "course_announcement",
            {
                "course_id": str(course.pk),
                "title": course.title,
                "announcement": "A new live session is added next month",
            },
            dedupe_key="seed:announcement",
        )
    ticket = SupportTicket.objects.filter(member=amaka).first()
    if ticket is not None:
        notify.notify(
            amaka.pk,
            "ticket_reply",
            {
                "ticket_id": str(ticket.pk),
                "reference": ticket.reference,
                "excerpt": "We are looking into your certificate now.",
            },
            dedupe_key="seed:ticket-reply",
        )


def seed_mentor_pricing() -> None:
    ada = person("ada@demo.test")
    profile = MentorProfile.objects.filter(user=ada).first()
    if profile is None:
        return
    mentor_setup.save_settings(
        user_id=ada.pk,
        data={
            "session_lengths": [30, 45, 60],
            "buffer_minutes": 10,
            "min_notice_hours": 12,
            "pricing_mode": "free",
        },
    )
    david = User.objects.filter(email="david@demo.test").first()
    if david is not None and MentorProfile.objects.filter(user=david).exists():
        mentor_setup.save_settings(
            user_id=david.pk,
            data={"pricing_mode": "paid", "default_price_minor": 2_000_000, "currency": "NGN"},
        )


def main() -> None:
    admin = person("admin@demo.test")
    seed_referrals()
    seed_courses(admin)
    seed_tickets(admin)
    seed_notifications()
    seed_mentor_pricing()
    print("Added referrals, courses, support requests, notifications and mentor pricing.")


if __name__ == "__main__":
    main()
