from django.urls import path

from apps.events import views

urlpatterns = [
    path("events", views.EventsView.as_view(), name="events"),
    path("events/<uuid:event_id>", views.EventView.as_view(), name="event"),
    path("events/<uuid:event_id>/register", views.RegisterView.as_view(), name="event-register"),
    path("events/<uuid:event_id>/calendar.ics", views.CalendarView.as_view(), name="event-ics"),
    path("public/events", views.PublicEventsView.as_view(), name="public-events"),
    path("public/events/<slug:slug>", views.PublicEventView.as_view(), name="public-event"),
]
