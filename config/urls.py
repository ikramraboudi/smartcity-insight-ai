from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from urgences.views import (
    creer_signalement,
    changer_statut_intervention,
    obtenir_audit_intervention,
    calculer_risk_map_zone,
    lister_zones_risk_map,
    lister_alertes,
    lister_casernes,
    obtenir_geo_config,
    simuler_accident,
    assistant_llm_decisionnel,
    endpoint_simulation_urgences,
    chantiers_list_create,
    chantier_detail,
    lister_troncons,
    troncons_proches,
)
from ml_congestion.api_views import predict_congestion_api, get_model_metrics_api

urlpatterns = [
    path('admin/', admin.site.urls),
    # Module Signalements Citoyens & Dashboard (Étudiant 2)
    path('api/signalements/', include('signalements.urls')),

    # Module Urgences & Protection Civile (Étudiant 3)
    path('api/urgences/geo-config/', obtenir_geo_config, name='obtenir_geo_config'),
    path('api/urgences/alertes/', lister_alertes, name='lister_alertes'),
    path('api/urgences/casernes/', lister_casernes, name='lister_casernes'),
    path('api/urgences/simuler-accident/', simuler_accident, name='simuler_accident'),
    path('api/urgences/signalement/', creer_signalement, name='creer_signalement'),
    path('api/urgences/recevoir-accident/', creer_signalement, name='recevoir_accident_etud2'),
    path('api/urgences/alerte/<int:alerte_id>/statut/', changer_statut_intervention, name='changer_statut_intervention'),
    path('api/urgences/alerte/<int:alerte_id>/audit/', obtenir_audit_intervention, name='obtenir_audit_intervention'),
    path('api/urgences/risk-map/', calculer_risk_map_zone, name='calculer_risk_map_zone'),
    path('api/urgences/risk-map/zones/', lister_zones_risk_map, name='lister_zones_risk_map'),
    path('api/urgences/assistant/', assistant_llm_decisionnel, name='assistant_llm_decisionnel'),
    path('api/urgences/simulate/', endpoint_simulation_urgences, name='endpoint_simulation_urgences'),

    # Gestion des Chantiers (Responsable Municipal -> Carte Protection Civile)
    path('api/chantiers/', chantiers_list_create, name='chantiers_list_create'),
    path('api/chantiers/<int:chantier_id>/', chantier_detail, name='chantier_detail'),

    # Base Spatiale PostGIS — Tronçons Routiers
    path('api/troncons/', lister_troncons, name='lister_troncons'),
    path('api/troncons/proches/', troncons_proches, name='troncons_proches'),

    # Module D — Prédiction de Congestion (Machine Learning)
    path('api/ml/congestion/predict/', predict_congestion_api, name='predict_congestion_ml'),
    path('api/ml/congestion/metrics/', get_model_metrics_api, name='get_model_metrics_ml'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

