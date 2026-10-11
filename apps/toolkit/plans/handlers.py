from apps.toolkit.jobs import services as jobs
from apps.toolkit.plans import service


def register() -> None:
    jobs.register("plan.generate", service.generate)
