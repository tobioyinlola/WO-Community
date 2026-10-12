"""Fills a local database with a believable community, so the web app has something to show.

Run from the repository root with the local settings:

    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_demo.py

Everything here is made up: names, companies, jobs and courses are not real. The script is safe to
run twice (it stops if the demo members already exist) and refuses to run outside local settings.
"""

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

from apps.accounts.models import User, UserRole, UserStatus  # noqa: E402
from apps.core.etag import etag_for  # noqa: E402
from apps.directory import services as directory  # noqa: E402
from apps.editorial import services as editorial  # noqa: E402
from apps.events import services as events  # noqa: E402
from apps.feed import services as feed  # noqa: E402
from apps.jobs import services as jobs  # noqa: E402
from apps.jobs.models import JobSettings  # noqa: E402
from apps.learning import authoring as learning  # noqa: E402
from apps.mentorship import availability  # noqa: E402
from apps.mentorship.models import MentorProfile  # noqa: E402
from apps.profiles import services as profiles  # noqa: E402
from apps.reference import selectors as reference  # noqa: E402
from apps.startups import services as startups  # noqa: E402

PASSWORD = "Demo-Passw0rd-2026"  # nosec B105  # noqa: S105  # local demo data only

MEMBERS = [
    # name, email, country, city, headline, startup (name, sector, stage, pitch), skills
    (
        "Amaka Obi",
        "amaka@demo.test",
        "NG",
        "Lagos",
        "Founder and CEO at Kuda Foods",
        (
            "Kuda Foods",
            "agritech",
            "seed",
            "Fresh produce from smallholder farms to city kitchens in a day.",
        ),
        ["product-management", "fundraising"],
    ),
    (
        "Tunde Kolade",
        "tunde@demo.test",
        "KE",
        "Nairobi",
        "Partner at Delta Capital",
        (
            "Delta Capital",
            "fintech",
            "series-a",
            "Early stage capital for African fintech founders.",
        ),
        ["fundraising", "finance"],
    ),
    (
        "Ngozi Eze",
        "ngozi@demo.test",
        "GH",
        "Accra",
        "Co-founder at Paylane",
        ("Paylane", "fintech", "pre-seed", "Payroll and instant wages for informal workers."),
        ["engineering", "product-management"],
    ),
    (
        "Jide Okafor",
        "jide@demo.test",
        "NG",
        "Abuja",
        "Operator, growth and partnerships",
        ("Shelf Africa", "ecommerce", "seed", "Inventory and ordering for neighbourhood shops."),
        ["marketing", "sales"],
    ),
    (
        "Zanele Mokoena",
        "zanele@demo.test",
        "ZA",
        "Cape Town",
        "Founder at SolarGrid",
        ("SolarGrid", "cleantech", "seed", "Pay-as-you-go solar for townships."),
        ["engineering", "operations"],
    ),
    (
        "Chidi Bello",
        "chidi@demo.test",
        "NG",
        "Lagos",
        "CTO at Medlink",
        ("Medlink", "healthtech", "pre-seed", "Book and pay for clinic visits from any phone."),
        ["engineering", "data"],
    ),
    (
        "Funmi Adeyemi",
        "funmi@demo.test",
        "NG",
        "Ibadan",
        "Founder at LearnLoop",
        ("LearnLoop", "edtech", "idea", "Exam practice that works offline on cheap phones."),
        ["design", "product-management"],
    ),
    (
        "Kwame Mensah",
        "kwame@demo.test",
        "GH",
        "Kumasi",
        "Founder at TroTro Track",
        ("TroTro Track", "logistics", "seed", "Live minibus times for commuters."),
        ["engineering", "operations"],
    ),
    (
        "Aisha Diallo",
        "aisha@demo.test",
        "SN",
        "Dakar",
        "Founder at Tisseo",
        ("Tisseo", "ecommerce", "seed", "A marketplace for West African textile makers."),
        ["marketing", "design"],
    ),
    (
        "Samuel Tesfaye",
        "samuel@demo.test",
        "ET",
        "Addis Ababa",
        "Operator at Habesha Pay",
        ("Habesha Pay", "fintech", "seed", "Cross-border remittances without the fees."),
        ["finance", "operations"],
    ),
]
MENTORS = [
    (
        "Ada Nwosu",
        "ada@demo.test",
        "NG",
        "Lagos",
        "Former CFO, now advising founders",
        ["fundraising", "pricing", "finance"],
        12,
        "Chief Financial Officer",
        "Interswitch",
    ),
    (
        "David Kamau",
        "david@demo.test",
        "KE",
        "Nairobi",
        "Product leader, two exits",
        ["product", "hiring", "growth"],
        15,
        "VP Product",
        "Twiga Foods",
    ),
    (
        "Thandi Nkosi",
        "thandi@demo.test",
        "ZA",
        "Johannesburg",
        "Operator who scaled to 10 countries",
        ["operations", "sales", "partnerships"],
        10,
        "COO",
        "Jumo",
    ),
]
ADMIN = ("Community Admin", "admin@demo.test")


def make_user(email: str, role: str = "member") -> User:
    user = User.objects.create_user(email, PASSWORD)
    user.status = UserStatus.ACTIVE
    user.email_verified_at = timezone.now()
    user.approved_at = timezone.now()
    user.save()
    UserRole.objects.get_or_create(user=user, role=role)
    return user


def make_waiting(email: str, *, email_confirmed: bool) -> User:
    """An account that has asked to join: waiting for approval, email confirmed or not."""
    user = User.objects.create_user(email, PASSWORD)
    user.status = UserStatus.PENDING
    user.email_verified_at = timezone.now() if email_confirmed else None
    user.save()
    if email_confirmed:
        UserRole.objects.get_or_create(user=user, role="member")
    return user


def make_profile(user: User, name: str, country: str, city: str, headline: str, skills: list[str]):
    profile = profiles.create_from_signup(
        user.pk, {"full_name": name, "country": country, "city": city}
    )
    known = {s.slug for s in reference.skills()}
    profiles.update_profile(
        user_id=user.pk,
        data={
            "headline": headline,
            "bio": f"{name} is building in {city}. Ask about what has worked and what has not.",
            "skills": [s for s in skills if s in known],
            "open_to": ["partnerships", "mentoring"],
        },
        if_match=etag_for(profile),
    )


def main() -> None:
    if User.objects.filter(email="amaka@demo.test").exists():
        print("Demo members already exist; nothing to do.")
        return

    admin = make_user(ADMIN[1], "super_admin")
    make_waiting("pending@demo.test", email_confirmed=True)
    make_waiting("unverified@demo.test", email_confirmed=False)
    people = []
    for name, email, country, city, headline, startup, skills in MEMBERS:
        user = make_user(email)
        make_profile(user, name, country, city, headline, skills)
        s_name, sector, stage, pitch = startup
        created = startups.create_startup(
            owner_id=user.pk,
            data={
                "name": s_name,
                "country": country,
                "city": city,
                "sector": sector,
                "stage": stage,
                "pitch": pitch,
            },
        )
        # List the startup and open the founder's basics, as a member who wants to be found would.
        startups.update_startup(
            user_id=user.pk,
            startup_id=created.pk,
            data={"directory_opt_in": True},
            if_match=etag_for(created),
        )
        profiles.update_visibility(user_id=user.pk, levels={"basics": "public", "bio": "public"})
        people.append(user)

    now = timezone.now()
    for name, email, country, city, headline, expertise, years, role, company in MENTORS:
        user = make_user(email, "mentor")
        make_profile(user, name, country, city, headline, [])
        MentorProfile.objects.create(
            user=user,
            about=f"{name} has {years} years of experience and mentors founders every week.",
            expertise=expertise,
            years_experience=years,
            current_role=role,
            company=company,
            industries=["fintech", "agritech"],
            stages=["idea", "pre-seed", "seed"],
            languages=["en"],
            timezone="Africa/Lagos",
            capacity_per_week=4,
            session_minutes=45,
            approved_at=now,
        )
        availability.replace(
            user_id=user.pk,
            data={
                "timezone": "Africa/Lagos",
                "weekly": [{"weekday": d, "start": "10:00", "end": "13:00"} for d in (1, 2, 3, 4)],
            },
        )

    # Posts and replies from the community.
    posts = [
        ("update", "We closed our first 40 paying shops this week. Slow, steady, and real."),
        ("question", "How are you pricing for customers who pay weekly, not monthly?"),
        ("win", "Shortlisted for a regional accelerator. Thank you to everyone who gave feedback."),
        ("resource", "A simple template for customer interviews that I use every time."),
        ("opportunity", "Looking for a part-time designer to help with our onboarding."),
    ]
    made = []
    for i, (category, body) in enumerate(posts):
        made.append(
            feed.create_post(
                user_id=people[i % len(people)].pk,
                category=category,
                body=f"<p>{body}</p>",
                images=[],
            )
        )

    # Jobs go live at once for the demo.
    board = JobSettings.load()
    board.require_approval = False
    board.save()
    for i, (title, kind, where, remote) in enumerate(
        [
            ("Senior backend engineer", "full_time", "Lagos, Nigeria", True),
            ("Growth marketing lead", "full_time", "Nairobi, Kenya", False),
            ("Product design intern", "internship", "Accra, Ghana", False),
            ("Operations associate", "contract", "Cape Town, South Africa", False),
        ]
    ):
        jobs.create_job(
            user_id=people[i].pk,
            data={
                "title": title,
                "type": kind,
                "location": where,
                "remote": remote,
                "organisation": MEMBERS[i][5][0],
                "description": (
                    f"<p>Join {MEMBERS[i][5][0]} and help us grow. You will own your work.</p>"
                ),
                "apply_method": "email",
                "apply_target": f"jobs@{MEMBERS[i][5][0].lower().replace(' ', '')}.test",
            },
            admin=False,
        )

    # Events.
    for _i, (kind, title, days) in enumerate(
        [
            ("demo_day", "Demo Day, Lagos", 14),
            ("workshop", "Fundraising basics", 6),
            ("meetup", "Founders breakfast, Nairobi", 21),
        ]
    ):
        event = events.create_event(
            actor=admin,
            data={
                "type": kind,
                "title": title,
                "description": (
                    f"<p>{title}. Come, meet the community and learn from each other.</p>"
                ),
                "timezone": "Africa/Lagos",
                "starts_at": now + timedelta(days=days, hours=2),
                "ends_at": now + timedelta(days=days, hours=5),
                "location": "Lagos, Nigeria",
                "capacity": 80,
                "public": True,
            },
        )
        events.publish(actor=admin, event_id=event.pk)

    # News.
    for title, kind in (
        ("Kuda Foods raises a seed round", "funding"),
        ("Three members win the regional founders award", "award"),
        ("Welcome to the new platform", "announcement"),
    ):
        item = editorial.create_item(
            actor=admin,
            data={
                "type": kind,
                "title": title,
                "body": f"<p>{title}. Read the full story from the community team.</p>",
                "public": True,
                "comments_enabled": True,
            },
        )
        editorial.publish_now(actor=admin, item_id=item.pk)

    # Courses.
    for title, category, level in (
        ("Founder fundamentals", "Foundations", "beginner"),
        ("Fundraising for African startups", "Funding", "intermediate"),
    ):
        course = learning.create_course(
            actor=admin,
            data={
                "title": title,
                "description": f"<p>{title}: practical lessons from people who have done it.</p>",
                "instructor": "WO Community faculty",
                "category": category,
                "level": level,
                "access": "free",
                "open_to_visitors": True,
                "certificate_enabled": True,
            },
        )
        module = learning.add_module(actor=admin, course_id=course.pk, title="Getting started")
        for n, lesson_title in enumerate(
            ("Why this matters", "The first steps", "Common mistakes"), 1
        ):
            learning.add_lesson(
                actor=admin,
                module_id=module.pk,
                data={
                    "type": "reading",
                    "title": lesson_title,
                    "duration_seconds": 300 * n,
                    "body": f"<p>{lesson_title}. Lesson text for {title}.</p>",
                },
            )
        learning.publish(actor=admin, course_id=course.pk)

    counts = directory.reconcile()
    print(f"Directory: {counts}")
    print(f"Seeded {len(MEMBERS)} members, {len(MENTORS)} mentors and an admin.")
    print(f"Sign in with any of them. Password: {PASSWORD}")
    print("  member:  amaka@demo.test")
    print("  mentor:  ada@demo.test")
    print("  admin:   admin@demo.test")


if __name__ == "__main__":
    main()
