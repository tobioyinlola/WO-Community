from django.apps import AppConfig


class CampaignsConfig(AppConfig):
    name = "apps.campaigns"
    label = "campaigns"

    def ready(self) -> None:
        from apps.campaigns import handlers, tasks  # noqa: F401
        from apps.campaigns.services import record_delivery
        from apps.notifications import services as notification_services

        handlers.register()
        notification_services.add_delivery_listener(record_delivery)
