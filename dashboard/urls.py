from django.urls import path
from . import views
from .views import telegram_test_backup, telegram_backup_settings_view, telegram_send_db_backup

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),  # صفحة لوحة التحكم الرئيسية
    path('home/stats/', views.home_stats_partial, name='home_stats_partial'),
    path('home/secondary-stats/', views.home_secondary_stats_partial, name='home_secondary_stats_partial'),
    path('home/alerts/', views.home_alerts_partial, name='home_alerts_partial'),
    path('home/latest-logs/', views.home_latest_logs_partial, name='home_latest_logs_partial'),
    path('home/top-ips/', views.home_top_ips_partial, name='home_top_ips_partial'),

    path("users/", views.users_management, name="users_management"),
    path("users/add/", views.add_user, name="add_user"),
    path("users/delete/<int:user_id>/", views.delete_user, name="delete_user"),
    path("users/edit/<int:user_id>/", views.edit_user, name="edit_user"),
    path("profile-settings/", views.profile_settings_view, name="profile_settings"),
    path("telegram-backup-settings/", telegram_backup_settings_view, name="telegram_backup_settings"),
    path("telegram-test/", telegram_test_backup, name="telegram_test"),
    path("telegram-send-db-backup/", telegram_send_db_backup, name="telegram_send_db_backup"),
]
