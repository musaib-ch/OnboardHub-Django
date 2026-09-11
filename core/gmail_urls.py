from django.urls import path

from .views import gmail_views

urlpatterns = [
    path("admin/settings/gmail/", gmail_views.gmail_settings, name="admin_gmail_settings"),
    path("admin/settings/gmail/callback/", gmail_views.gmail_callback, name="admin_gmail_callback"),
]
