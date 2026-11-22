"""
Module D — Moteur d'Inférence & Logique Métier (Section 7.4)
SmartCity Insight AI — Prédiction de Congestion Urbaine.

Implémente les 3 fonctionnalités clés exigées par le cahier des charges :
1. Estimation du risque de congestion par rue et par créneau horaire
2. Estimation de l'impact d'un chantier sur la circulation
3. Recommandation d'itinéraires alternatifs lorsque les données le permettent
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import joblib
import pandas as pd
import numpy as np

from .data_pipeline import TUNIS_STREETS, STREETS_BY_ID, get_creneau_horaire
from .train import train_and_evaluate_models, ALL_FEATURES

MODELS_DIR = "ml_congestion/models"
REGRESSOR_PATH = os.path.join(MODELS_DIR, "best_congestion_regressor.joblib")
CLASSIFIER_PATH = os.path.join(MODELS_DIR, "best_congestion_classifier.joblib")

_regressor = None
_classifier = None


def load_trained_models():
    """Charge en mémoire les modèles entraînés ou lance l'entraînement automatique s'ils n'existent pas."""
    global _regressor, _classifier
    if _regressor is not None and _classifier is not None:
        return _regressor, _classifier

    if not os.path.exists(REGRESSOR_PATH) or not os.path.exists(CLASSIFIER_PATH):
        print("⚡ Modèles introuvables. Lancement de l'entraînement automatique...")
        train_and_evaluate_models()

    _regressor = joblib.load(REGRESSOR_PATH)
    _classifier = joblib.load(CLASSIFIER_PATH)
    return _regressor, _classifier


def _build_features_row(
    street: Dict[str, Any],
    dt: datetime,
    has_work: int,
    meteo_pluie: int,
    incidents_recents: int = 1,
) -> Dict[str, Any]:
    """Construit un dictionnaire de variables explicatives pour une rue à une date/heure donnée."""
    hour = dt.hour
    minute = dt.minute
    creneau = get_creneau_horaire(hour)
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week in [5, 6] else 0
    is_rush = 1 if (creneau in ["POINTE_MATIN", "POINTE_SOIR"] and not is_weekend) else 0

    return {
        "street_id": street["street_id"],
        "road_type": street["road_type"],
        "creneau_horaire": creneau,
        "hour": hour,
        "minute": minute,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "is_rush_hour": is_rush,
        "base_speed_kmh": street["base_speed_kmh"],
        "length_km": street["length_km"],
        "proximity_sensitive": street["proximity_sensitive"],
        "presence_travaux": has_work,
        "meteo_pluie": meteo_pluie,
        "incidents_recents": incidents_recents,
    }


def predict_congestion_by_street(
    simulation_datetime: str,
    chantiers: Optional[List[str]] = None,
    meteo_pluie: int = 0,
    incidents_by_street: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Fonctionnalité 1 (7.4) : Estimation du risque de congestion par rue et par créneau horaire.
    
    Prend en entrée la date de la simulation et retourne pour chaque rue l'indicateur précis :
    - Indice de congestion continu (1.0 à 5.0)
    - Score de risque de congestion (0 à 100%)
    - Classe de congestion (FLUIDE, MODERE, ELEVE, CRITIQUE)
    - Code couleur pour la cartographie
    - Vitesse moyenne estimée et durée de parcours
    """
    regressor, classifier = load_trained_models()

    if isinstance(chantiers, str):
        chantiers = [chantiers] if chantiers.strip() else []
    elif chantiers is None:
        chantiers = []
    if incidents_by_street is None:
        incidents_by_street = {}

    dt = datetime.fromisoformat(simulation_datetime)
    rows = []
    for st in TUNIS_STREETS:
        has_work = 1 if st["street_id"] in chantiers else 0
        incidents = incidents_by_street.get(st["street_id"], 1 if has_work else 0)
        rows.append(_build_features_row(st, dt, has_work, meteo_pluie, incidents))

    df_features = pd.DataFrame(rows)[ALL_FEATURES]

    # Inférence Machine Learning
    pred_indices = regressor.predict(df_features)
    pred_classes = classifier.predict(df_features)

    results = []
    for i, st in enumerate(TUNIS_STREETS):
        idx = round(float(np.clip(pred_indices[i], 1.0, 5.0)), 2)
        score_pct = round(float(((idx - 1.0) / 4.0) * 100.0), 1)
        cls = str(pred_classes[i])

        if idx < 2.0:
            color = "#10b981"  # Vert (Fluide)
        elif idx < 3.2:
            color = "#f59e0b"  # Jaune / Orange (Modéré)
        elif idx < 4.2:
            color = "#ef4444"  # Rouge (Élevé)
        else:
            color = "#991b1b"  # Rouge foncé (Critique / Bloqué)

        speed_factor = max(0.12, 1.0 - ((idx - 1.0) / 4.0) * 0.85)
        est_speed = round(st["base_speed_kmh"] * speed_factor, 1)
        est_duration = round((st["length_km"] / max(5.0, est_speed)) * 60.0, 1)
        nom_duration = round((st["length_km"] / st["base_speed_kmh"]) * 60.0, 1)
        est_delay = max(0.0, round(est_duration - nom_duration, 1))

        has_work = st["street_id"] in chantiers

        results.append({
            "street_id": st["street_id"],
            "street_name": st["street_name"],
            "zone": st["zone"],
            "road_type": st["road_type"],
            "has_worksite": has_work,
            "meteo_pluie": meteo_pluie,
            # Indicateur Précis
            "congestion_index": idx,
            "congestion_risk_pct": score_pct,
            "congestion_class": cls,
            "color": color,
            "estimated_speed_kmh": est_speed,
            "base_speed_kmh": st["base_speed_kmh"],
            "estimated_duration_min": est_duration,
            "estimated_delay_min": est_delay,
            "alternatives": st.get("alternatives", []),
        })

    return results


def estimate_worksite_impact(
    street_id: str,
    simulation_datetime: str,
    meteo_pluie: int = 0,
) -> Dict[str, Any]:
    """
    Fonctionnalité 2 (7.4) : Estimation de l'impact d'un chantier sur la circulation.
    
    Calcule le surcroît de temps de trajet et l'élévation du risque de congestion
    provoqués spécifiquement par l'implantation d'un chantier sur une artère donnée :
    Δ = Prédiction(avec travaux) - Prédiction(sans travaux)
    """
    st = STREETS_BY_ID.get(street_id)
    if not st:
        raise ValueError(f"Rue inconnue : {street_id}")

    regressor, classifier = load_trained_models()
    dt = datetime.fromisoformat(simulation_datetime)

    # Condition 1 : SANS travaux (référence)
    row_no_work = _build_features_row(st, dt, has_work=0, meteo_pluie=meteo_pluie, incidents_recents=0)
    df_no_work = pd.DataFrame([row_no_work])[ALL_FEATURES]
    idx_no_work = round(float(np.clip(regressor.predict(df_no_work)[0], 1.0, 5.0)), 2)
    cls_no_work = str(classifier.predict(df_no_work)[0])

    # Condition 2 : AVEC travaux (chantier actif)
    row_with_work = _build_features_row(st, dt, has_work=1, meteo_pluie=meteo_pluie, incidents_recents=2)
    df_with_work = pd.DataFrame([row_with_work])[ALL_FEATURES]
    idx_with_work = round(float(np.clip(regressor.predict(df_with_work)[0], 1.0, 5.0)), 2)
    cls_with_work = str(classifier.predict(df_with_work)[0])

    # Calcul des différentiels (Δ)
    risk_pct_no_work = round(((idx_no_work - 1.0) / 4.0) * 100.0, 1)
    risk_pct_with_work = round(((idx_with_work - 1.0) / 4.0) * 100.0, 1)
    delta_risk_pct = round(risk_pct_with_work - risk_pct_no_work, 1)
    delta_index = round(idx_with_work - idx_no_work, 2)

    # Impact sur le temps de trajet
    speed_no_work = st["base_speed_kmh"] * max(0.12, 1.0 - ((idx_no_work - 1.0) / 4.0) * 0.85)
    speed_with_work = st["base_speed_kmh"] * max(0.12, 1.0 - ((idx_with_work - 1.0) / 4.0) * 0.85)
    duration_no_work = (st["length_km"] / max(5.0, speed_no_work)) * 60.0
    duration_with_work = (st["length_km"] / max(5.0, speed_with_work)) * 60.0
    additional_delay_min = max(0.0, round(duration_with_work - duration_no_work, 1))

    return {
        "street_id": street_id,
        "street_name": st["street_name"],
        "simulation_datetime": simulation_datetime,
        "baseline_without_worksite": {
            "congestion_index": idx_no_work,
            "congestion_risk_pct": risk_pct_no_work,
            "congestion_class": cls_no_work,
            "estimated_speed_kmh": round(speed_no_work, 1),
            "estimated_duration_min": round(duration_no_work, 1),
        },
        "with_worksite": {
            "congestion_index": idx_with_work,
            "congestion_risk_pct": risk_pct_with_work,
            "congestion_class": cls_with_work,
            "estimated_speed_kmh": round(speed_with_work, 1),
            "estimated_duration_min": round(duration_with_work, 1),
        },
        "worksite_impact_delta": {
            "delta_congestion_index": delta_index,
            "delta_risk_pct": f"+{delta_risk_pct}%",
            "additional_delay_minutes": f"+{additional_delay_min} min",
            "speed_drop_kmh": f"-{round(speed_no_work - speed_with_work, 1)} km/h",
            "impact_level": "CRITIQUE" if delta_risk_pct >= 25 else "SIGNIFICATIF" if delta_risk_pct >= 15 else "MODERE",
        },
        "interpretation": (
            f"L'implantation d'un chantier sur {st['street_name']} génère un surcroît de risque "
            f"de +{delta_risk_pct}% et un retard additionnel moyen de +{additional_delay_min} minutes "
            f"pour le créneau horaire analysé ({dt.strftime('%Hh%M')})."
        ),
    }


def recommend_alternative_routes(
    street_id: str,
    simulation_datetime: str,
    chantiers: Optional[List[str]] = None,
    meteo_pluie: int = 0,
) -> Dict[str, Any]:
    """
    Fonctionnalité 3 (7.4) : Recommandation d'itinéraires alternatifs lorsque les données le permettent.
    
    Lorsque l'axe analysé présente un risque de congestion élevé ou critique (>= 50%),
    évalue les axes de délestage potentiels pour ce même créneau horaire et recommande
    l'itinéraire alternatif optimal avec gain de temps estimé.
    """
    st = STREETS_BY_ID.get(street_id)
    if not st:
        raise ValueError(f"Rue inconnue : {street_id}")

    if isinstance(chantiers, str):
        chantiers = [chantiers] if chantiers.strip() else []
    elif chantiers is None:
        chantiers = []

    # Prédiction complète de toutes les artères pour le créneau
    all_preds = predict_congestion_by_street(simulation_datetime, chantiers, meteo_pluie)
    preds_map = {p["street_id"]: p for p in all_preds}

    target_pred = preds_map[street_id]
    candidate_ids = st.get("alternatives", [])

    candidates_eval = []
    for cand_id in candidate_ids:
        if cand_id in preds_map:
            c_pred = preds_map[cand_id]
            candidates_eval.append({
                "street_id": cand_id,
                "street_name": c_pred["street_name"],
                "zone": c_pred["zone"],
                "congestion_risk_pct": c_pred["congestion_risk_pct"],
                "congestion_class": c_pred["congestion_class"],
                "estimated_speed_kmh": c_pred["estimated_speed_kmh"],
                "estimated_duration_min": c_pred["estimated_duration_min"],
                "has_worksite": c_pred["has_worksite"],
            })

    # Trier par risque de congestion croissant
    candidates_eval.sort(key=lambda x: x["congestion_risk_pct"])

    is_congested = target_pred["congestion_risk_pct"] >= 50.0 or target_pred["congestion_class"] in ["ELEVE", "CRITIQUE"]

    best_alternative = None
    time_saved_min = 0.0
    recommendation_text = ""

    if candidates_eval and is_congested:
        best_cand = candidates_eval[0]
        if best_cand["congestion_risk_pct"] < target_pred["congestion_risk_pct"]:
            best_alternative = best_cand
            time_saved_min = max(0.0, round(target_pred["estimated_delay_min"] - (best_cand["estimated_duration_min"] * 0.15), 1))
            recommendation_text = (
                f"Axe principal ({target_pred['street_name']}) saturé ({target_pred['congestion_risk_pct']}% de risque). "
                f"Déviation vivement conseillée par : {best_cand['street_name']} "
                f"(Risque : {best_cand['congestion_risk_pct']}%, statut {best_cand['congestion_class']}). "
                f"Gain estimé : ~{time_saved_min} minutes."
            )
        else:
            recommendation_text = "Corridors alternatifs également chargés. Prioriser le maintien sur l'artère avec feux régulés."
    elif not is_congested:
        recommendation_text = f"L'axe {target_pred['street_name']} est actuellement fluide ({target_pred['congestion_risk_pct']}% de risque). Aucun itinéraire alternatif nécessaire."
    else:
        recommendation_text = "Aucun axe de délestage direct répertorié pour ce tronçon."

    return {
        "analyzed_street": {
            "street_id": street_id,
            "street_name": target_pred["street_name"],
            "congestion_risk_pct": target_pred["congestion_risk_pct"],
            "congestion_class": target_pred["congestion_class"],
            "estimated_delay_min": target_pred["estimated_delay_min"],
            "has_worksite": target_pred["has_worksite"],
        },
        "simulation_datetime": simulation_datetime,
        "is_congested": is_congested,
        "recommended_alternative": best_alternative,
        "alternative_candidates": candidates_eval,
        "estimated_time_saved_min": time_saved_min,
        "recommendation_summary": recommendation_text,
    }
