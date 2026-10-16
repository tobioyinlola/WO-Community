"""Adds what the admin console needs to the local demo community.

Run it after `scripts/seed_demo.py`, from the repository root, with the local settings:

    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_admin_demo.py

It is safe to run again. Each run:

* makes sure `admin@demo.test` has two step sign in switched on, using a key every developer
  knows (it is worked out from a phrase below, so the browser tests can compute the same codes);
* makes sure `editor@demo.test` (a content editor with no two step sign in yet) exists, which is
  what the enrolment screen is tested with;
* adds two people waiting for approval, with the profile and startup they gave;
* makes the job board hold new jobs for review, then adds a job waiting for review, a reported
  post and a win waiting for review.

Everything is made up and the script refuses to run outside local development.
"""

import base64
import os
import sys
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

from apps.accounts.models import MfaDevice, User, UserRole, UserStatus  # noqa: E402
from apps.core import crypto  # noqa: E402
from apps.editorial import services as editorial  # noqa: E402
from apps.feed import moderation  # noqa: E402
from apps.feed import services as feed  # noqa: E402
from apps.jobs import services as jobs  # noqa: E402
from apps.jobs.models import JobSettings  # noqa: E402
from apps.profiles import services as profiles  # noqa: E402
from apps.startups import services as startups  # noqa: E402

PASSWORD = "Demo-Passw0rd-2026"  # nosec B105  # noqa: S105  # local demo data only
# The demo admin authenticator key, worked out from a phrase so no key-shaped text is stored.
PHRASE = b"wo community demo admin"
ADMIN_TOTP_KEY = base64.b32encode(PHRASE).decode().rstrip("=")


def person(email: str, role: str) -> User:
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email, PASSWORD)
    user.status = UserStatus.ACTIVE
    user.email_verified_at = user.email_verified_at or timezone.now()
    user.approved_at = user.approved_at or timezone.now()
    user.save()
    UserRole.objects.get_or_create(user=user, role=role)
    return user


APPLICANTS = [
    (
        "Ifeoma Eze",
        "NG",
        "Enugu",
        "Zuri Pay",
        "fintech",
        "seed",
        "Savings groups, moved onto a phone.",
    ),
    (
        "Kofi Annan-Boateng",
        "GH",
        "Accra",
        "Cocoa Trace",
        "agritech",
        "pre-seed",
        "Tracing cocoa from farm to bar.",
    ),
]


def applicant(stamp: str, n: int, row: tuple[str, str, str, str, str, str, str]) -> None:
    """A person waiting for approval, with the profile and startup they gave on joining."""
    name, country, city, startup, sector, stage, pitch = row
    user = User.objects.create_user(f"applicant{n}.{stamp}@demo.test", PASSWORD)
    user.status = UserStatus.PENDING
    user.email_verified_at = timezone.now()
    user.save()
    UserRole.objects.get_or_create(user=user, role="member")
    # Sign up asks for LinkedIn and the company website, and approval needs LinkedIn.
    handle = "-".join(name.lower().split())
    profiles.create_from_signup(
        user.pk,
        {
            "full_name": name,
            "country": country,
            "city": city,
            "linkedin_url": f"https://www.linkedin.com/in/{handle}-{stamp}",
        },
    )
    startups.create_from_signup(
        user.pk,
        {
            "name": f"{startup} {stamp}",
            "country": country,
            "city": city,
            "sector": sector,
            "stage": stage,
            "pitch": pitch,
            "website_url": f"https://{''.join(startup.lower().split())}.example.com",
        },
    )


def main() -> None:
    admin = person("admin@demo.test", "super_admin")
    MfaDevice.objects.update_or_create(
        user=admin,
        defaults={
            "secret_encrypted": crypto.encrypt(ADMIN_TOTP_KEY),
            "confirmed_at": timezone.now(),
            "last_used_step": 0,
        },
    )
    person("editor@demo.test", "content_editor")

    board = JobSettings.load()
    board.require_approval = True
    board.save()

    kwame = User.objects.get(email="kwame@demo.test")
    samuel = User.objects.get(email="samuel@demo.test")
    chidi = User.objects.get(email="chidi@demo.test")
    stamp = timezone.now().strftime("%H%M%S")
    for n, row in enumerate(APPLICANTS, start=1):
        applicant(stamp, n, row)

    jobs.create_job(
        user_id=samuel.pk,
        data={
            "title": f"Finance analyst {stamp}",
            "type": "full_time",
            "location": "Addis Ababa, Ethiopia",
            "remote": False,
            "organisation": "Habesha Pay",
            "description": "<p>Join Habesha Pay and keep our books straight as we grow.</p>",
            "apply_method": "email",
            "apply_target": "jobs@habeshapay.test",
        },
    )
    post = feed.create_post(
        user_id=kwame.pk, category="update", body=f"Buy followers cheap {stamp}", images=[]
    )
    moderation.report(
        viewer=chidi,
        target_type="post",
        target_id=post.pk,
        reason="spam",
        details="Looks like an advert.",
    )
    editorial.submit_win(
        user_id=kwame.pk,
        data={
            "kind": "partnership",
            "title": f"First 1,000 riders {stamp}",
            "evidence_url": "https://example.com/proof",
            "details": "We passed 1,000 weekly riders.",
        },
    )
    print(
        "Admin demo data ready. Sign in as admin@demo.test with the demo password and the demo key."
    )


if __name__ == "__main__":
    main()
