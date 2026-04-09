from django.urls import path
from . import views
from .views import telegram_test_backup, telegram_backup_settings_view, telegram_send_db_backup

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),  # صفحة لوحة التحكم الرئيسية

    path("telegram-backup-settings/", telegram_backup_settings_view, name="telegram_backup_settings"),
    path("telegram-test/", telegram_test_backup, name="telegram_test"),
    path("telegram-send-db-backup/", telegram_send_db_backup, name="telegram_send_db_backup"),
]
