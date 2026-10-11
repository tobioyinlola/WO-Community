from apps.toolkit.jobs import services as jobs
from apps.toolkit.prototypes import service


def register() -> None:
    jobs.register("prototype.generate", service.generate)
