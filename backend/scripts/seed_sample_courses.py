"""Adds three sample courses to a local database, one for each shape the course creator makes.

Run from the backend folder with the local settings:

    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_sample_courses.py

- "Sample: one video" is a single video in a single module, published, with no cover image.
- "Sample: three modules" is a published course with three modules and several videos.
- "Sample: draft in progress" is a draft with one module and one video that members cannot see.

The videos are public YouTube links with their titles written here, so no network is needed.
Safe to run twice (a sample that exists is left as it is) and refuses to run outside local settings.
Run `scripts/seed_demo.py` first: the courses are made by its admin account.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

if not settings.DEBUG:
    sys.exit("Refusing to seed sample courses outside local development.")

from apps.accounts.models import User  # noqa: E402
from apps.learning import authoring as learning  # noqa: E402
from apps.learning.models import Course  # noqa: E402

# (title, what it is, published, modules: [(module title, [(lesson title, YouTube link, seconds)])])
SAMPLES = [
    (
        "Sample: one video",
        "A course with one module and one video. It has no cover image and is still complete.",
        True,
        [("Start here", [("A single lesson", "https://youtu.be/dQw4w9WgXcQ", 213)])],
    ),
    (
        "Sample: three modules",
        "A longer course: three modules, each with a few videos, to try the outline and progress.",
        True,
        [
            (
                "Module 1: Getting started",
                [
                    ("Welcome", "https://youtu.be/dQw4w9WgXcQ", 213),
                    ("How this course works", "https://www.youtube.com/watch?v=aqz-KE-bpKQ", 635),
                ],
            ),
            (
                "Module 2: The basics",
                [
                    ("The first idea", "https://youtu.be/9bZkp7q19f0", 252),
                    ("Putting it to use", "https://www.youtube.com/shorts/jNQXAC9IVRw", 19),
                ],
            ),
            (
                "Module 3: Going further",
                [("Where to go next", "https://youtu.be/dQw4w9WgXcQ", 213)],
            ),
        ],
    ),
    (
        "Sample: draft in progress",
        "A draft. Only editors can see it, so members never find it while it is being written.",
        False,
        [("Module 1", [("Work in progress", "https://youtu.be/9bZkp7q19f0", 252)])],
    ),
]


def main() -> None:
    admin = User.objects.filter(email="admin@demo.test").first()
    if admin is None:
        sys.exit("Run scripts/seed_demo.py first: the demo admin account is missing.")
    for title, summary, published, modules in SAMPLES:
        if Course.objects.filter(title=title).exists():
            print(f"Left as it is: {title}")
            continue
        course = learning.create_course(
            actor=admin,
            data={
                "title": title,
                "description": f"<p>{summary}</p>",
                "instructor": "WO Community faculty",
                "category": "Samples",
                "level": "all",
                "access": "free",
                "certificate_enabled": True,
            },
        )
        for module_title, lessons in modules:
            module = learning.add_module(actor=admin, course_id=course.pk, title=module_title)
            for lesson_title, link, seconds in lessons:
                learning.add_lesson(
                    actor=admin,
                    module_id=module.pk,
                    data={
                        "type": "video",
                        "title": lesson_title,
                        "video_url": link,
                        "duration_seconds": seconds,
                    },
                )
        if published:
            learning.publish(actor=admin, course_id=course.pk)
        print(f"Made: {title} ({'published' if published else 'draft'})")


if __name__ == "__main__":
    main()
