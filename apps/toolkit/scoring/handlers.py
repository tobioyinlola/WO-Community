from apps.toolkit.jobs import services as jobs
from apps.toolkit.scoring import service


def register() -> None:
    jobs.register("score.generate", service.generate)
