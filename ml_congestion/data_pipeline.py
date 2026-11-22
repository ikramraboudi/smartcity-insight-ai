"""
Module D — Pipeline de Données & Création de Variables (Sections 8.1, 8.2, 8.4)
SmartCity Insight AI — Prédiction de Congestion Urbaine (Grand Tunis).

Sources de données :
- Source A : historique des travaux (chantiers), signalements citoyens, incidents et accidents
- Source B : géométrie, longueur, typologie et vitesse nominale des 12 artères de Tunis
- Source C : calendrier (date, heure, jour de la semaine, créneaux) et météo (pluie)
"""

import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np
import pandas as pd

# Source B : Spécifications des 12 artères métropolitaines du Grand Tunis
TUNIS_STREETS: List[Dict[str, Any]] = [
    {
        "street_id": "seg_bourguiba",
        "street_name": "Avenue Habib Bourguiba & Avenue de France",
        "zone": "TUNIS_CENTRE",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 40.0,
        "length_km": 2.1,
        "proximity_sensitive": 1,
        "alternatives": ["seg_liberte_thameur", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_mohamed_v",
        "street_name": "Avenue Mohamed V",
        "zone": "TUNIS_CENTRE",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 50.0,
        "length_km": 2.8,
        "proximity_sensitive": 1,
        "alternatives": ["seg_liberte_thameur", "seg_berges_du_lac"],
    },
    {
        "street_id": "seg_route_x_sud",
        "street_name": "Route X — Tronçon Sud (Bardo / Bab Saadoun)",
        "zone": "BARDO",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 70.0,
        "length_km": 4.2,
        "proximity_sensitive": 0,
        "alternatives": ["seg_liberte_thameur", "seg_route_x_nord"],
    },
    {
        "street_id": "seg_route_x_nord",
        "street_name": "Route X — Tronçon Nord (El Manar / Campus)",
        "zone": "EL_MANAR",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 75.0,
        "length_km": 4.5,
        "proximity_sensitive": 1,
        "alternatives": ["seg_gp8_ariana", "seg_ariana_centre"],
    },
    {
        "street_id": "seg_rn9_marsa_ouest",
        "street_name": "RN9 — Route de La Marsa (Tunis Marine ➔ Lac 1)",
        "zone": "LAC",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 80.0,
        "length_km": 3.9,
        "proximity_sensitive": 0,
        "alternatives": ["seg_berges_du_lac", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_rn9_marsa_est",
        "street_name": "RN9 — Route de La Marsa (Lac 2 ➔ Ain Zaghouan ➔ Marsa)",
        "zone": "BANLIEUE_NORD",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 90.0,
        "length_km": 6.8,
        "proximity_sensitive": 0,
        "alternatives": ["seg_goulette_roosevelt", "seg_berges_du_lac"],
    },
    {
        "street_id": "seg_sortie_sud_bab_alioua",
        "street_name": "Sortie Sud & GP1 — Échangeur Bab Alioua",
        "zone": "BANLIEUE_SUD",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 65.0,
        "length_km": 3.5,
        "proximity_sensitive": 0,
        "alternatives": ["seg_bourguiba", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_gp8_ariana",
        "street_name": "GP8 — Route de Bizerte (Ariana Ouest)",
        "zone": "ARIANA",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 60.0,
        "length_km": 5.1,
        "proximity_sensitive": 0,
        "alternatives": ["seg_route_x_nord", "seg_ariana_centre"],
    },
    {
        "street_id": "seg_berges_du_lac",
        "street_name": "Boulevard Principal des Berges du Lac 1",
        "zone": "LAC",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 45.0,
        "length_km": 2.6,
        "proximity_sensitive": 0,
        "alternatives": ["seg_rn9_marsa_ouest"],
    },
    {
        "street_id": "seg_ariana_centre",
        "street_name": "Avenue Taïeb Mhiri (Ariana Centre)",
        "zone": "ARIANA",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 45.0,
        "length_km": 2.4,
        "proximity_sensitive": 1,
        "alternatives": ["seg_gp8_ariana", "seg_route_x_nord"],
    },
    {
        "street_id": "seg_liberte_thameur",
        "street_name": "Avenue de la Liberté & Bab El Khadra",
        "zone": "TUNIS_CENTRE",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 40.0,
        "length_km": 2.2,
        "proximity_sensitive": 1,
        "alternatives": ["seg_mohamed_v", "seg_bourguiba"],
    },
    {
        "street_id": "seg_goulette_roosevelt",
        "street_name": "Avenue Franklin Roosevelt (La Goulette / Le Kram)",
        "zone": "BANLIEUE_NORD",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 50.0,
        "length_km": 3.2,
        "proximity_sensitive": 0,
        "alternatives": ["seg_rn9_marsa_est"],
    },
]

STREETS_BY_ID = {s["street_id"]: s for s in TUNIS_STREETS}


def get_creneau_horaire(hour: int) -> str:
    """Affecte le libellé du créneau horaire selon l'heure (8.4)."""
    if 0 <= hour < 7:
        return "NUIT"
    elif 7 <= hour < 10:
        return "POINTE_MATIN"
    elif 10 <= hour < 12:
        return "CREUSE_MATIN"
    elif 12 <= hour < 14:
        return "DEJEUNER"
    elif 14 <= hour < 16:
        return "APRES_MIDI"
    elif 16 <= hour < 20:
        return "POINTE_SOIR"
    else:
        return "SOIREE"


def build_chronological_dataset(
    start_date: str = "2026-08-01",
    days: int = 90,
    csv_path: str = "ml_congestion/data/traffic_historical_dataset.csv",
) -> pd.DataFrame:
    """
    Construit le jeu de données chronologique complet (25 920 lignes).
    Respecte l'ordre temporel pour permettre une séparation apprentissage/test rigoureuse (8.5).
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    random.seed(42)
    np.random.seed(42)

    start_dt = datetime.fromisoformat(start_date)
    records = []

    # Simulation d'épisodes de chantiers réalistes (Source A)
    works_calendar = {
        "seg_route_x_sud": [(10, 35), (60, 80)],
        "seg_mohamed_v": [(25, 45)],
        "seg_bourguiba": [(50, 70)],
        "seg_rn9_marsa_ouest": [(15, 30)],
        "seg_gp8_ariana": [(40, 65)],
    }

    # Jours pluvieux (~16% du calendrier - Source C)
    rainy_days = set(random.sample(range(days), k=int(days * 0.16)))

    for day_idx in range(days):
        current_date = start_dt + timedelta(days=day_idx)
        day_of_week = current_date.weekday()
        is_weekend = 1 if day_of_week in [5, 6] else 0
        is_rain = 1 if day_idx in rainy_days else 0

        for hour in range(24):
            creneau = get_creneau_horaire(hour)
            is_rush = 1 if (creneau in ["POINTE_MATIN", "POINTE_SOIR"] and not is_weekend) else 0

            for st in TUNIS_STREETS:
                st_id = st["street_id"]

                # 1. Présence de travaux (Chantier)
                has_work = 0
                if st_id in works_calendar:
                    for s_d, e_d in works_calendar[st_id]:
                        if s_d <= day_idx <= e_d:
                            has_work = 1
                            break

                # 2. Incidents récents
                inc_prob = 0.05 + (0.16 if is_rush else 0) + (0.12 if has_work else 0) + (0.10 if is_rain else 0)
                incidents_recents = int(min(8, np.random.poisson(lam=max(0.2, inc_prob * 3.5))))

                # 3. Modélisation de l'indicateur de congestion (physique urbaine de Tunis)
                base_idx = 1.25

                if creneau == "POINTE_MATIN":
                    if st["zone"] in ["TUNIS_CENTRE", "BARDO", "EL_MANAR"]:
                        base_idx += 2.25 if not is_weekend else 0.50
                    else:
                        base_idx += 1.65 if not is_weekend else 0.40
                elif creneau == "POINTE_SOIR":
                    if st["zone"] in ["BANLIEUE_NORD", "BANLIEUE_SUD", "LAC", "ARIANA"]:
                        base_idx += 2.35 if not is_weekend else 0.70
                    else:
                        base_idx += 1.70 if not is_weekend else 0.45
                elif creneau == "DEJEUNER":
                    base_idx += 0.85
                elif creneau in ["CREUSE_MATIN", "APRES_MIDI"]:
                    base_idx += 0.50
                elif creneau == "SOIREE":
                    base_idx += 0.40
                    if is_weekend and st["zone"] in ["LAC", "BANLIEUE_NORD"]:
                        base_idx += 1.15

                # Type de route & zone sensible
                if st["road_type"] == "VOIE_URBAINE" and st["proximity_sensitive"]:
                    base_idx += 0.35

                # Impact chantier (+0.95 à +1.45 d'indice)
                if has_work:
                    base_idx += random.uniform(0.95, 1.45)

                # Impact météo pluie (+0.45 à +0.80)
                if is_rain:
                    base_idx += random.uniform(0.45, 0.80)

                # Impact incidents récents
                base_idx += incidents_recents * 0.22

                # Bruit stochastique
                noise = np.random.normal(loc=0.0, scale=0.18)
                idx = round(float(np.clip(base_idx + noise, 1.0, 5.0)), 2)

                # Score en pourcentage (0 à 100%)
                risk_pct = round(float(((idx - 1.0) / 4.0) * 100.0), 2)

                # Classification en 4 classes
                if idx < 2.0:
                    cls = "FLUIDE"
                elif idx < 3.2:
                    cls = "MODERE"
                elif idx < 4.2:
                    cls = "ELEVE"
                else:
                    cls = "CRITIQUE"

                # Durée et retard
                speed_ratio = max(0.12, 1.0 - ((idx - 1.0) / 4.0) * 0.85)
                vitesse = round(st["base_speed_kmh"] * speed_ratio, 1)
                duree = round((st["length_km"] / max(5.0, vitesse)) * 60.0, 2)
                duree_nominale = round((st["length_km"] / st["base_speed_kmh"]) * 60.0, 2)
                retard = max(0.0, round(duree - duree_nominale, 2))

                dt = current_date.replace(hour=hour, minute=0, second=0)

                records.append({
                    "timestamp": dt.isoformat(),
                    "date": dt.strftime("%Y-%m-%d"),
                    "hour": hour,
                    "minute": 0,
                    "creneau_horaire": creneau,
                    "day_of_week": day_of_week,
                    "is_weekend": is_weekend,
                    "is_rush_hour": is_rush,
                    "street_id": st_id,
                    "street_name": st["street_name"],
                    "zone": st["zone"],
                    "road_type": st["road_type"],
                    "base_speed_kmh": st["base_speed_kmh"],
                    "length_km": st["length_km"],
                    "proximity_sensitive": st["proximity_sensitive"],
                    "presence_travaux": has_work,
                    "meteo_pluie": is_rain,
                    "incidents_recents": incidents_recents,
                    "vitesse_relevee_kmh": vitesse,
                    "duree_trajet_min": duree,
                    "delay_minutes": retard,
                    # Targets
                    "congestion_index": idx,
                    "congestion_risk_pct": risk_pct,
                    "congestion_class": cls,
                })

    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    print(f"✅ Pipeline données prêt : {len(df)} observations créées ({csv_path})")
    return df


def load_dataset(csv_path: str = "ml_congestion/data/traffic_historical_dataset.csv") -> pd.DataFrame:
    """Charge le jeu de données ou le génère s'il n'existe pas encore."""
    if not os.path.exists(csv_path):
        return build_chronological_dataset(csv_path=csv_path)
    return pd.read_csv(csv_path)
