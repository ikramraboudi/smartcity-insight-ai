"""
Module D — Pipeline de Données & Création de Variables (Sections 8.1, 8.2, 8.4)
SmartCity Insight AI — Prédiction de Congestion Routière
Zone : Nord-Est du Cap Bon (Kélibia, Hammam El Ghezaz, El Haouaria, Dar Allouche, Kerkouane, Azmour, Menzel Horr).
"""

import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np
import pandas as pd

# Source B : Spécifications des 8 corridors routiers du Nord-Est Cap Bon
CAP_BON_STREETS: List[Dict[str, Any]] = [
    {
        "street_id": "seg_kelibia_centre",
        "street_name": "Avenue des Martyrs & Place du Marché (Kélibia)",
        "zone": "KELIBIA",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 45.0,
        "length_km": 2.8,
        "proximity_sensitive": 1,
        "alternatives": ["seg_kelibia_port_mansourah", "seg_azmour_carrefour"],
    },
    {
        "street_id": "seg_kelibia_port_mansourah",
        "street_name": "Route du Port & Corniche El Mansourah (Kélibia)",
        "zone": "KELIBIA",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 50.0,
        "length_km": 3.6,
        "proximity_sensitive": 1,
        "alternatives": ["seg_kelibia_centre", "seg_hammam_ghezeze_c27"],
    },
    {
        "street_id": "seg_hammam_ghezeze_c27",
        "street_name": "Route Côtière C27 — Kélibia / Hammam El Ghezaz",
        "zone": "HAMMAM_GHEZEZE",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 55.0,
        "length_km": 5.4,
        "proximity_sensitive": 1,
        "alternatives": ["seg_kelibia_port_mansourah", "seg_dar_allouche_c27"],
    },
    {
        "street_id": "seg_dar_allouche_c27",
        "street_name": "C27 Nord — Hammam El Ghezaz / Dar Allouche",
        "zone": "DAR_ALLOUCHE",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 60.0,
        "length_km": 5.8,
        "proximity_sensitive": 0,
        "alternatives": ["seg_hammam_ghezeze_c27", "seg_kerkouane_littoral"],
    },
    {
        "street_id": "seg_kerkouane_littoral",
        "street_name": "Route Littorale — Dar Allouche / Kerkouane",
        "zone": "KERKOUANE",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 60.0,
        "length_km": 4.9,
        "proximity_sensitive": 0,
        "alternatives": ["seg_dar_allouche_c27", "seg_el_haouaria_centre"],
    },
    {
        "street_id": "seg_el_haouaria_centre",
        "street_name": "Route d'El Haouaria (C27 / Route des Grottes)",
        "zone": "EL_HAOUARIA",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 50.0,
        "length_km": 6.4,
        "proximity_sensitive": 1,
        "alternatives": ["seg_kerkouane_littoral", "seg_azmour_carrefour"],
    },
    {
        "street_id": "seg_azmour_carrefour",
        "street_name": "Liaison Ouest — Kélibia / Azmour (Route de Takelsa)",
        "zone": "AZMOUR",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 70.0,
        "length_km": 7.5,
        "proximity_sensitive": 0,
        "alternatives": ["seg_kelibia_centre", "seg_menzel_horr_mc27"],
    },
    {
        "street_id": "seg_menzel_horr_mc27",
        "street_name": "Corridor MC27 — Kélibia / Menzel Horr",
        "zone": "MENZEL_HORR",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 75.0,
        "length_km": 11.2,
        "proximity_sensitive": 0,
        "alternatives": ["seg_azmour_carrefour", "seg_kelibia_centre"],
    },
]

TUNIS_STREETS = CAP_BON_STREETS
STREETS_BY_ID = {s["street_id"]: s for s in CAP_BON_STREETS}


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
    Construit le jeu de données chronologique complet (90 * 24 * 8 = 17 280 observations)
    pour le Nord-Est du Cap Bon.
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    random.seed(42)
    np.random.seed(42)

    start_dt = datetime.fromisoformat(start_date)
    records = []

    works_calendar = {
        "seg_menzel_horr_mc27": [(10, 35), (60, 80)],
        "seg_kelibia_centre": [(25, 45)],
        "seg_hammam_ghezeze_c27": [(50, 70)],
        "seg_el_haouaria_centre": [(15, 30)],
        "seg_azmour_carrefour": [(40, 65)],
    }

    rainy_days = set(random.sample(range(days), k=int(days * 0.16)))

    for day_idx in range(days):
        current_date = start_dt + timedelta(days=day_idx)
        day_of_week = current_date.weekday()
        is_weekend = 1 if day_of_week in [5, 6] else 0
        is_rain = 1 if day_idx in rainy_days else 0

        for hour in range(24):
            creneau = get_creneau_horaire(hour)
            is_rush = 1 if (creneau in ["POINTE_MATIN", "POINTE_SOIR"] and not is_weekend) else 0

            for st in CAP_BON_STREETS:
                st_id = st["street_id"]

                has_work = 0
                if st_id in works_calendar:
                    for s_d, e_d in works_calendar[st_id]:
                        if s_d <= day_idx <= e_d:
                            has_work = 1
                            break

                inc_prob = 0.05 + (0.16 if is_rush else 0) + (0.12 if has_work else 0) + (0.10 if is_rain else 0)
                incidents_recents = int(min(8, np.random.poisson(lam=max(0.2, inc_prob * 3.5))))

                base_idx = 1.20

                if creneau == "POINTE_MATIN":
                    if st["zone"] in ["KELIBIA", "MENZEL_HORR"]:
                        base_idx += 2.20 if not is_weekend else 0.55
                    else:
                        base_idx += 1.45 if not is_weekend else 0.40
                elif creneau == "POINTE_SOIR":
                    if st["zone"] in ["HAMMAM_GHEZEZE", "DAR_ALLOUCHE", "EL_HAOUARIA", "AZMOUR"]:
                        base_idx += 2.15 if not is_weekend else 0.85
                    else:
                        base_idx += 1.65 if not is_weekend else 0.50
                elif creneau == "DEJEUNER":
                    base_idx += 0.80
                elif creneau in ["CREUSE_MATIN", "APRES_MIDI"]:
                    base_idx += 0.45
                elif creneau == "SOIREE":
                    base_idx += 0.35
                    if is_weekend and st["zone"] in ["KELIBIA", "HAMMAM_GHEZEZE", "EL_HAOUARIA"]:
                        base_idx += 1.15

                if st["road_type"] == "VOIE_URBAINE" and st["proximity_sensitive"]:
                    base_idx += 0.35

                if has_work:
                    base_idx += random.uniform(0.95, 1.45)

                if is_rain:
                    base_idx += random.uniform(0.45, 0.80)

                base_idx += incidents_recents * 0.22

                noise = np.random.normal(loc=0.0, scale=0.18)
                idx = round(float(np.clip(base_idx + noise, 1.0, 5.0)), 2)
                risk_pct = round(float(((idx - 1.0) / 4.0) * 100.0), 2)

                if idx < 2.0:
                    cls = "FLUIDE"
                elif idx < 3.2:
                    cls = "MODERE"
                elif idx < 4.2:
                    cls = "ELEVE"
                else:
                    cls = "CRITIQUE"

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
                    "congestion_index": idx,
                    "congestion_risk_pct": risk_pct,
                    "congestion_class": cls,
                })

    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    print(f"✅ Pipeline données Nord-Est Cap Bon prêt : {len(df)} observations créées ({csv_path})")
    return df


def load_dataset(csv_path: str = "ml_congestion/data/traffic_historical_dataset.csv") -> pd.DataFrame:
    """Charge le jeu de données ou le génère s'il n'existe pas encore."""
    if not os.path.exists(csv_path):
        return build_chronological_dataset(csv_path=csv_path)
    return pd.read_csv(csv_path)
