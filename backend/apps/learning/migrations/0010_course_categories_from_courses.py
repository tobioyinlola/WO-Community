"""Every category a course already uses becomes an entry in the course category list.

Categories used to be typed freely on each course; now they are picked from a list the admins
manage. This keeps what is there (0-to-1, say) so no course loses its category, spelled as the
first course to use it spelled it.
"""

from django.db import migrations
from django.db.models import Max
from django.utils.text import slugify


def import_categories(apps, schema_editor):
    Course = apps.get_model("learning", "Course")
    CourseCategory = apps.get_model("reference", "CourseCategory")
    top = CourseCategory.objects.aggregate(top=Max("sort_order"))["top"] or 0
    for name in Course.objects.order_by("created_at").values_list("category", flat=True):
        name = (name or "").strip()
        if not name or CourseCategory.objects.filter(name__iexact=name).exists():
            continue
        base = slugify(name)[:72] or "category"
        slug, n = base, 2
        while CourseCategory.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        top += 1
        CourseCategory.objects.create(name=name[:80], slug=slug, sort_order=top)


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0009_enrolment_ended_at"),
        ("reference", "0004_course_categories"),
    ]

    operations = [migrations.RunPython(import_categories, migrations.RunPython.noop)]
