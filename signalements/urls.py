from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnomalieAcquitterView,
    AnomalieAnalyseView,
    AnomalieListView,
    CurrentUserProfileView,
    LoginSignalementView,
    RegisterSignalementView,
    SignalementViewSet,
)

router = DefaultRouter()
router.register(r'', SignalementViewSet, basename='signalement')

urlpatterns = [
    path('auth/login/', LoginSignalementView.as_view(), name='signalements_login'),
    path('auth/register/', RegisterSignalementView.as_view(), name='signalements_register'),
    path('auth/me/', CurrentUserProfileView.as_view(), name='signalements_me'),
    path('anomalies/', AnomalieListView.as_view(), name='signalements_anomalies'),
    path('anomalies/analyser/', AnomalieAnalyseView.as_view(), name='signalements_anomalies_analyser'),
    path('anomalies/<int:pk>/acquitter/', AnomalieAcquitterView.as_view(), name='signalements_anomalies_acquitter'),
    path('', include(router.urls)),
]
