from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        from apps.accounts import schema  # noqa: F401
