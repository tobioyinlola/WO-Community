"""The first testimonials for the home page: founders Onyeka has mentored, in their own words.

Each was published, with the person's name and role, on Onyeka's own site, and is copied here as
written. Running this again adds nothing twice, and removing it takes away only these rows.
"""

from django.db import migrations

TESTIMONIALS = [
    (
        "Your guidance and mentorship has been pivotal, shaping me into the entrepreneur I am "
        "today, and fuelling my journey to build Retna Africa and Earlybean (Techstars ’23).",
        "Tomiwa Allan Ogunmodede",
        "Co-Founder, Retna Africa and EarlyBean, United Arab Emirates",
    ),
    (
        "Safe to say that Onyeka Akumah is one of the greatest teachers out there !!!",
        "Linda Obi",
        "CEO AfriHealth & Forbes Council Member, United Kingdom",
    ),
    (
        "One day, you'd write of us your mentees, how you have helped us navigate our own "
        "startups!",
        "Jumoke Oduwole",
        "CEO, Alajo App, Nigeria",
    ),
    (
        "Onyeka is a brilliant mentor of startups from Africa with over 60 startups mentored",
        "Sunil Sharma",
        "MD, Techstars Toronto, Canada",
    ),
    (
        "You are a brilliant mentor of entrepreneurs and I enjoyed working with you.",
        "Isidore Kpotufe",
        "CEO & Founder, RIVIA Health, Ghana",
    ),
    (
        "Working with you changed my perspective on business. I would do it again and again. You "
        "were not just an inspiration, you gave me the room to express myself completely and "
        "that is something I will never forget. Thank you Onyeka.",
        "Benaiah Rawlings",
        "CEO, ZeaHomes, Ghana",
    ),
]


def add(apps, schema_editor):
    Testimonial = apps.get_model("editorial", "Testimonial")
    for position, (quote, name, role) in enumerate(TESTIMONIALS, start=1):
        Testimonial.objects.get_or_create(
            name=name,
            quote=quote,
            defaults={
                "role": role,
                "position": position,
                "published": True,
                "consent_confirmed": True,
            },
        )


def remove(apps, schema_editor):
    Testimonial = apps.get_model("editorial", "Testimonial")
    for quote, name, _ in TESTIMONIALS:
        Testimonial.objects.filter(name=name, quote=quote).delete()


class Migration(migrations.Migration):

    dependencies = [("editorial", "0004_testimonials")]

    operations = [migrations.RunPython(add, remove)]
