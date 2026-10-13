from celery import shared_task

from apps.adminconsole import dashboard, stale_alerts


@shared_task(name="adminconsole.refresh_dashboard")
def refresh_dashboard(days: int = 2) -> int:
    """Rebuild the dashboard summary tables for the last ``days`` days."""
    return dashboard.refresh(days=days)


@shared_task(name="adminconsole.send_stale_summary")
def send_stale_summary() -> int:
    """Once a day, tell each admin about approvals that have waited more than 24 hours."""
    return stale_alerts.send_stale_summary()
