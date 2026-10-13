from django.db import migrations
from django.db.models import Count, Sum


def fill_counts(apps, schema_editor):
    """Courses that existed before the counts were kept get them worked out once."""
    Course = apps.get_model("learning", "Course")
    Enrolment = apps.get_model("learning", "Enrolment")
    Lesson = apps.get_model("learning", "Lesson")
    learners = dict(
        Enrolment.objects.values_list("course_id")
        .annotate(n=Count("id"))
        .values_list("course_id", "n")
    )
    seconds = dict(
        Lesson.objects.values_list("course_id")
        .annotate(s=Sum("duration_seconds"))
        .values_list("course_id", "s")
    )
    for course in Course.objects.all():
        course.learners_count = learners.get(course.pk, 0)
        course.total_duration_seconds = seconds.get(course.pk) or 0
        course.save(update_fields=["learners_count", "total_duration_seconds"])


class Migration(migrations.Migration):
    dependencies = [("learning", "0003_lms_fields")]

    operations = [migrations.RunPython(fill_counts, migrations.RunPython.noop)]
