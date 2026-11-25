"""
Vues API Django REST pour le Module D — Prédiction de Congestion.
Permet aux autres membres de l'équipe (ou au frontend) d'appeler le modèle ML facilement.
"""

import json
import os
from datetime import datetime
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .predictor import (
    predict_congestion_by_street,
    estimate_worksite_impact,
    recommend_alternative_routes,
)


@api_view(["POST"])
def predict_congestion_api(request):
    """
    Endpoint principal du Module D (7.4) :
    Prend en entrée la date/heure de la simulation, les chantiers et la météo.
    Retourne :
    1. Le risque de congestion par rue et par créneau
    2. L'estimation de l'impact des chantiers
    3. Les recommandations d'itinéraires alternatifs
    """
    data = request.data or {}
    simulation_dt = data.get("simulation_datetime", datetime.now().isoformat())
    chantiers_raw = data.get("chantiers", [])
    if hasattr(data, "getlist") and not isinstance(chantiers_raw, list):
        chantiers = data.getlist("chantiers") or ([chantiers_raw] if chantiers_raw else [])
    elif isinstance(chantiers_raw, str):
        if "," in chantiers_raw:
            chantiers = [s.strip() for s in chantiers_raw.split(",") if s.strip()]
        elif chantiers_raw.strip():
            chantiers = [chantiers_raw.strip()]
        else:
            chantiers = []
    elif isinstance(chantiers_raw, (list, tuple)):
        chantiers = list(chantiers_raw)
    else:
        chantiers = []

    meteo_pluie = int(data.get("meteo_pluie", 0))

    # 1. Estimation du risque par rue et créneau
    predictions = predict_congestion_by_street(
        simulation_datetime=simulation_dt,
        chantiers=chantiers,
        meteo_pluie=meteo_pluie,
    )

    # 2. Estimation de l'impact des chantiers actifs
    worksite_impacts = []
    for st_id in chantiers:
        try:
            impact = estimate_worksite_impact(
                street_id=st_id,
                simulation_datetime=simulation_dt,
                meteo_pluie=meteo_pluie,
            )
            worksite_impacts.append(impact)
        except Exception:
            pass

    # 3. Recommandations d'itinéraires alternatifs pour les artères saturées
    alternative_recommendations = []
    for pred in predictions:
        if pred["congestion_risk_pct"] >= 50.0 or pred["congestion_class"] in ["ELEVE", "CRITIQUE"]:
            try:
                rec = recommend_alternative_routes(
                    street_id=pred["street_id"],
                    simulation_datetime=simulation_dt,
                    chantiers=chantiers,
                    meteo_pluie=meteo_pluie,
                )
                if rec.get("recommended_alternative"):
                    alternative_recommendations.append(rec)
            except Exception:
                pass

    return Response({
        "status": "success",
        "module": "Module D — Prédiction de Congestion",
        "simulation_datetime": simulation_dt,
        "meteo_pluie": meteo_pluie,
        "active_worksites_count": len(chantiers),
        "predictions": predictions,
        "worksite_impacts": worksite_impacts,
        "alternative_recommendations": alternative_recommendations,
    })


@api_view(["GET"])
def get_model_metrics_api(request):
    """
    Retourne les métriques d'évaluation du modèle (8.5) :
    Comparaison Random Forest vs Gradient Boosting, MAE, RMSE, F1-Score et Feature Importances.
    """
    cached = cache.get("ml_congestion_metrics")
    if cached is not None:
        return Response(cached)

    report_path = "ml_congestion/reports/model_evaluation.json"
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        cache.set("ml_congestion_metrics", metrics, timeout=3600)
        return Response(metrics)
    return Response({"error": "Rapport non trouvé. Veuillez lancer l'entraînement."}, status=404)
