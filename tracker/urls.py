from django.urls import path
from .views import LogVisitorAPIView

urlpatterns = [
    path('api/log/', LogVisitorAPIView.as_view(), name='log-visitor'),
]