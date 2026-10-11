from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.toolkit.jobs"
    label = "tk_jobs"

    def ready(self) -> None:
        from apps.core import metrics
        from apps.toolkit.jobs import exports, tasks  # noqa: F401
        from apps.toolkit.ventures import services as ventures

        metrics.add_collector(exports.queue_gauges)
        ventures.register_eraser(exports.erase_for)
        ventures.register_exporter("generated_files", exports.export_listing)
