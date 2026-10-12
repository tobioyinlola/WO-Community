from django.urls import path

from apps.support import views

urlpatterns = [
    path("support/contact", views.PublicContactView.as_view(), name="support-contact"),
    path("support/tickets", views.TicketsView.as_view(), name="support-tickets"),
    path("support/tickets/<uuid:ticket_id>", views.TicketView.as_view(), name="support-ticket"),
    path(
        "support/tickets/<uuid:ticket_id>/messages",
        views.TicketMessagesView.as_view(),
        name="support-ticket-messages",
    ),
    path(
        "support/tickets/<uuid:ticket_id>/reopen",
        views.TicketReopenView.as_view(),
        name="support-ticket-reopen",
    ),
    path(
        "support/tickets/<uuid:ticket_id>/feedback",
        views.TicketFeedbackView.as_view(),
        name="support-ticket-feedback",
    ),
    path(
        "support/attachments/<uuid:attachment_id>/download",
        views.AttachmentDownloadView.as_view(),
        name="support-attachment",
    ),
]
