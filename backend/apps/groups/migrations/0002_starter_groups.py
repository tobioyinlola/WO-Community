from django.db import migrations

STARTERS = [
    (
        "WO Men's Group",
        "👨🏾‍💼",
        "A space for the men of WO Community to talk business, life and growth.",
    ),
    (
        "WO Women's Group",
        "👩🏾‍💼",
        "A space for the women of WO Community to connect, share and lift each other up.",
    ),
    ("WO Sport Group", "⚽", "Matches, fitness and the games we love. Banter welcome."),
]


def add(apps, schema_editor):
    ChatGroup = apps.get_model("groups", "ChatGroup")
    for sort, (name, emoji, description) in enumerate(STARTERS, start=1):
        if not ChatGroup.objects.filter(name__iexact=name).exists():
            ChatGroup.objects.create(name=name, emoji=emoji, description=description, sort=sort)


class Migration(migrations.Migration):
    dependencies = [("groups", "0001_chat_groups")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
