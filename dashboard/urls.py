from django.urls import path

from .views.backup_views import (
    telegram_backup_settings_view,
    telegram_send_db_backup,
    telegram_test_backup,
)
from .views.home_views import (
    dashboard_home,
    home_alerts_partial,
    home_latest_logs_partial,
    home_secondary_stats_partial,
    home_stats_partial,
    home_top_ips_partial,
)
from .views.profile_views import profile_settings_view, regenerate_api_key_view
from .views.user_views import add_user, delete_user, edit_user, users_management

app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_home, name='home'),  # صفحة لوحة التحكم الرئيسية
    path('home/stats/', home_stats_partial, name='home_stats_partial'),
    path('home/secondary-stats/', home_secondary_stats_partial, name='home_secondary_stats_partial'),
    path('home/alerts/', home_alerts_partial, name='home_alerts_partial'),
    path('home/latest-logs/', home_latest_logs_partial, name='home_latest_logs_partial'),
    path('home/top-ips/', home_top_ips_partial, name='home_top_ips_partial'),

    path("users/", users_management, name="users_management"),
    path("users/add/", add_user, name="add_user"),
    path("users/delete/<int:user_id>/", delete_user, name="delete_user"),
    path("users/edit/<int:user_id>/", edit_user, name="edit_user"),
    path("profile-settings/", profile_settings_view, name="profile_settings"),
    path(
        "profile-settings/regenerate-api-key/",
        regenerate_api_key_view,
        name="regenerate_api_key",
    ),
    path("telegram-backup-settings/", telegram_backup_settings_view, name="telegram_backup_settings"),
    path("telegram-test/", telegram_test_backup, name="telegram_test"),
    path("telegram-send-db-backup/", telegram_send_db_backup, name="telegram_send_db_backup"),
]
