from celery import shared_task

from apps.adminconsole import dashboard


@shared_task(name="adminconsole.refresh_dashboard")
def refresh_dashboard(days: int = 2) -> int:
    """Rebuild the dashboard summary tables for the last ``days`` days."""
    return dashboard.refresh(days=days)
