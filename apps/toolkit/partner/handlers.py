from apps.toolkit.jobs import services as jobs
from apps.toolkit.partner import service


def register() -> None:
    jobs.register("partner.reply", service.reply)
