"""
Générateur et fusionneur de données historiques pour le Module D (Prédiction de Congestion).
Conforme aux sections 8.1, 8.2 et 8.4 du cahier des charges :
- Source A : historique des travaux, incidents et signalements
- Source B : géométrie et caractéristiques des 12 artères du Grand Tunis
- Source C : calendrier, créneaux horaires, météo et type de route
"""

import math
import random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Source B : Spécifications géographiques et routières des 12 artères de Tunis
STREETS_SPEC = [
    {
        "street_id": "seg_bourguiba",
        "street_name": "Avenue Habib Bourguiba & Avenue de France",
        "zone": "TUNIS_CENTRE",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 40.0,
        "length_km": 2.1,
        "proximity_sensitive": 1,
        "alternative_street_ids": ["seg_liberte_thameur", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_mohamed_v",
        "street_name": "Avenue Mohamed V",
        "zone": "TUNIS_CENTRE",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 50.0,
        "length_km": 2.8,
        "proximity_sensitive": 1,
        "alternative_street_ids": ["seg_liberte_thameur", "seg_berges_du_lac"],
    },
    {
        "street_id": "seg_route_x_sud",
        "street_name": "Route X — Tronçon Sud (Bardo / Bab Saadoun)",
        "zone": "BARDO",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 70.0,
        "length_km": 4.2,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_liberte_thameur", "seg_route_x_nord"],
    },
    {
        "street_id": "seg_route_x_nord",
        "street_name": "Route X — Tronçon Nord (El Manar / Campus)",
        "zone": "EL_MANAR",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 75.0,
        "length_km": 4.5,
        "proximity_sensitive": 1,
        "alternative_street_ids": ["seg_gp8_ariana", "seg_ariana_centre"],
    },
    {
        "street_id": "seg_rn9_marsa_ouest",
        "street_name": "RN9 — Route de La Marsa (Tunis Marine ➔ Lac 1)",
        "zone": "LAC",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 80.0,
        "length_km": 3.9,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_berges_du_lac", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_rn9_marsa_est",
        "street_name": "RN9 — Route de La Marsa (Lac 2 ➔ Ain Zaghouan ➔ Marsa)",
        "zone": "BANLIEUE_NORD",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 90.0,
        "length_km": 6.8,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_goulette_roosevelt", "seg_berges_du_lac"],
    },
    {
        "street_id": "seg_sortie_sud_bab_alioua",
        "street_name": "Sortie Sud & GP1 — Échangeur Bab Alioua",
        "zone": "BANLIEUE_SUD",
        "road_type": "VOIE_RAPIDE",
        "base_speed_kmh": 65.0,
        "length_km": 3.5,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_bourguiba", "seg_mohamed_v"],
    },
    {
        "street_id": "seg_gp8_ariana",
        "street_name": "GP8 — Route de Bizerte (Ariana Ouest)",
        "zone": "ARIANA",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 60.0,
        "length_km": 5.1,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_route_x_nord", "seg_ariana_centre"],
    },
    {
        "street_id": "seg_berges_du_lac",
        "street_name": "Boulevard Principal des Berges du Lac 1",
        "zone": "LAC",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 45.0,
        "length_km": 2.6,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_rn9_marsa_ouest"],
    },
    {
        "street_id": "seg_ariana_centre",
        "street_name": "Avenue Taïeb Mhiri (Ariana Centre)",
        "zone": "ARIANA",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 45.0,
        "length_km": 2.4,
        "proximity_sensitive": 1,
        "alternative_street_ids": ["seg_gp8_ariana", "seg_route_x_nord"],
    },
    {
        "street_id": "seg_liberte_thameur",
        "street_name": "Avenue de la Liberté & Bab El Khadra",
        "zone": "TUNIS_CENTRE",
        "road_type": "VOIE_URBAINE",
        "base_speed_kmh": 40.0,
        "length_km": 2.2,
        "proximity_sensitive": 1,
        "alternative_street_ids": ["seg_mohamed_v", "seg_bourguiba"],
    },
    {
        "street_id": "seg_goulette_roosevelt",
        "street_name": "Avenue Franklin Roosevelt (La Goulette / Le Kram)",
        "zone": "BANLIEUE_NORD",
        "road_type": "ARTERE_PRINCIPALE",
        "base_speed_kmh": 50.0,
        "length_km": 3.2,
        "proximity_sensitive": 0,
        "alternative_street_ids": ["seg_rn9_marsa_est"],
    },
]


def determine_creneau_horaire(hour: int) -> str:
    """Affecte le créneau horaire normalisé selon l'heure de la journée."""
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


def generate_historical_dataset(
    start_date: str = "2026-08-01",
    days: int = 90,
    output_path: str = "ml_congestion/data/traffic_historical_dataset.csv",
) -> pd.DataFrame:
    """
    Génère un jeu de données chronologique complet et réaliste pour l'apprentissage ML.
    Couvre 90 jours consécutifs avec 24 créneaux horaires par jour pour les 12 artères.
    Total : 90 * 24 * 12 = 25 920 observations.
    """
    random.seed(42)
    np.random.seed(42)

    start_dt = datetime.fromisoformat(start_date)
    records = []

    # Simulation d'épisodes de chantiers (travaux de voirie sur certains tronçons pour quelques semaines)
    active_works_schedule = {
        "seg_route_x_sud": [(10, 35), (60, 80)],        # travaux jour 10 à 35 et 60 à 80
        "seg_mohamed_v": [(25, 45)],                     # réfection trottoirs/éclairage
        "seg_bourguiba": [(50, 70)],                     # aménagement urbain
        "seg_rn9_marsa_ouest": [(15, 30)],               # élargissement bretelle
        "seg_gp8_ariana": [(40, 65)],                    # travaux voirie Ariana
    }

    # Simulation de jours de pluie (environ 15% des jours)
    rainy_days = set(random.sample(range(days), k=int(days * 0.16)))

    for day_offset in range(days):
        current_date = start_dt + timedelta(days=day_offset)
        day_of_week = current_date.weekday()  # 0=Lundi, 6=Dimanche
        is_weekend = 1 if day_of_week in [5, 6] else 0
        is_rainy = 1 if day_offset in rainy_days else 0

        for hour in range(24):
            creneau = determine_creneau_horaire(hour)
            is_rush = 1 if (creneau in ["POINTE_MATIN", "POINTE_SOIR"] and not is_weekend) else 0

            for street in STREETS_SPEC:
                st_id = street["street_id"]

                # 1. Présence de travaux (Chantiers)
                has_work = 0
                if st_id in active_works_schedule:
                    for start_d, end_d in active_works_schedule[st_id]:
                        if start_d <= day_offset <= end_d:
                            has_work = 1
                            break

                # 2. Incidents récents (accidents / pannes)
                # Plus fréquent en heure de pointe ou lors d'intempéries
                incident_prob = 0.05 + (0.15 if is_rush else 0) + (0.12 if has_work else 0) + (0.10 if is_rainy else 0)
                incidents_recents = np.random.poisson(lam=max(0.2, incident_prob * 3.5))
                incidents_recents = int(min(8, incidents_recents))

                # 3. Calcul de la charge de trafic de base (physique urbaine de Tunis)
                base_idx = 1.2  # Trafic libre de nuit

                # Biais créneau horaire
                if creneau == "POINTE_MATIN":
                    # Fort trafic vers Tunis Centre, Route X, Ariana
                    if street["zone"] in ["TUNIS_CENTRE", "BARDO", "EL_MANAR"]:
                        base_idx += 2.2 if not is_weekend else 0.5
                    else:
                        base_idx += 1.6 if not is_weekend else 0.4
                elif creneau == "POINTE_SOIR":
                    # Fort trafic de retour vers Marsa, Ariana, Banlieue Sud
                    if street["zone"] in ["BANLIEUE_NORD", "BANLIEUE_SUD", "LAC", "ARIANA"]:
                        base_idx += 2.3 if not is_weekend else 0.7
                    else:
                        base_idx += 1.7 if not is_weekend else 0.5
                elif creneau == "DEJEUNER":
                    base_idx += 0.8
                elif creneau in ["CREUSE_MATIN", "APRES_MIDI"]:
                    base_idx += 0.5
                elif creneau == "SOIREE":
                    base_idx += 0.4
                    if is_weekend and street["zone"] in ["LAC", "BANLIEUE_NORD"]:
                        base_idx += 1.1  # Sorties du samedi soir aux Berges du Lac / Marsa

                # Biais type de route
                if street["road_type"] == "VOIE_URBAINE" and street["proximity_sensitive"]:
                    base_idx += 0.3  # Centre-ville dense avec feux et piétons

                # Impact direct du chantier (+0.9 à +1.4)
                if has_work:
                    base_idx += random.uniform(0.9, 1.4)

                # Impact direct de la pluie (+0.4 à +0.8)
                if is_rainy:
                    base_idx += random.uniform(0.4, 0.8)

                # Impact des incidents récents (+0.25 par incident)
                base_idx += incidents_recents * 0.25

                # Aléa stochastique
                noise = np.random.normal(loc=0.0, scale=0.18)
                raw_idx = base_idx + noise

                # Borner l'indice de congestion entre 1.0 (fluide) et 5.0 (paralysé)
                congestion_index = round(float(np.clip(raw_idx, 1.0, 5.0)), 2)

                # Score de risque de congestion (0 à 100%)
                congestion_risk_pct = round(float(((congestion_index - 1.0) / 4.0) * 100.0), 2)

                # Classe de congestion
                if congestion_index < 2.0:
                    congestion_class = "FLUIDE"
                elif congestion_index < 3.2:
                    congestion_class = "MODERE"
                elif congestion_index < 4.2:
                    congestion_class = "ELEVE"
                else:
                    congestion_class = "CRITIQUE"

                # Vitesse observée et durée de trajet relevée
                speed_factor = max(0.12, 1.0 - ((congestion_index - 1.0) / 4.0) * 0.85)
                vitesse_relevee_kmh = round(street["base_speed_kmh"] * speed_factor, 1)
                duree_trajet_min = round((street["length_km"] / max(5.0, vitesse_relevee_kmh)) * 60.0, 2)
                duree_nominale_min = round((street["length_km"] / street["base_speed_kmh"]) * 60.0, 2)
                delay_minutes = max(0.0, round(duree_trajet_min - duree_nominale_min, 2))

                record_dt = current_date.replace(hour=hour, minute=0, second=0)

                records.append({
                    "timestamp": record_dt.isoformat(),
                    "date": record_dt.strftime("%Y-%m-%d"),
                    "hour": hour,
                    "minute": 0,
                    "creneau_horaire": creneau,
                    "day_of_week": day_of_week,
                    "is_weekend": is_weekend,
                    "is_rush_hour": is_rush,
                    "street_id": st_id,
                    "street_name": street["street_name"],
                    "zone": street["zone"],
                    "road_type": street["road_type"],
                    "base_speed_kmh": street["base_speed_kmh"],
                    "length_km": street["length_km"],
                    "proximity_sensitive": street["proximity_sensitive"],
                    "presence_travaux": has_work,
                    "meteo_pluie": is_rainy,
                    "incidents_recents": incidents_recents,
                    "vitesse_relevee_kmh": vitesse_relevee_kmh,
                    "duree_trajet_min": duree_trajet_min,
                    "delay_minutes": delay_minutes,
                    # Targets ML
                    "congestion_index": congestion_index,
                    "congestion_risk_pct": congestion_risk_pct,
                    "congestion_class": congestion_class,
                })

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)
    print(f"✅ Jeu de données historique généré : {len(df)} lignes sauvegardées dans {output_path}")
    return df


if __name__ == "__main__":
    generate_historical_dataset()
