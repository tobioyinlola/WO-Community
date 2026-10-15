from apps.toolkit.advisor import service
from apps.toolkit.jobs import services as jobs


def register() -> None:
    jobs.register("advisor.reply", service.reply)
