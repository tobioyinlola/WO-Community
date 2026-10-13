from django.apps import AppConfig


class DecksConfig(AppConfig):
    name = "apps.toolkit.decks"
    label = "tk_decks"

    def ready(self) -> None:
        from apps.toolkit.decks import handlers

        handlers.register()
