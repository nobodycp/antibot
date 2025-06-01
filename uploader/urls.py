# uploader/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('files/', views.file_list, name='uploader_files'),
]
