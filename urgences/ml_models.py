"""
Moteur Prédictif Risk Map (0 - 100 %) pour la Protection Civile du Cap Bon.
Combine :
1. L'historique des accidents enregistrés dans la zone (base de données réelle + distance Haversine).
2. La géométrie / criticité du tronçon (échangeur, carrefour giratoire, axe régional).
3. Le niveau de trafic / congestion (interconnecté avec le module ml_congestion).
"""

from datetime import timedelta
import math
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from django.utils import timezone

from config.geo_config import SECTEURS_CAP_BON
from .services import distance_metres

# Alias conservé pour la rétro-compatibilité d'imports internes
SECTEURS_REGION = SECTEURS_CAP_BON
SECTEURS_TUNIS = SECTEURS_CAP_BON

_risk_model_instance = None


def entrainer_modele_risk_map():
    """Entraîne et met en cache le modèle Random Forest pour l'estimation de probabilité de risque."""
    global _risk_model_instance
    if _risk_model_instance is not None:
        return _risk_model_instance

    data = {
        'trafic_index': [1.0, 1.4, 2.0, 2.5, 3.2, 3.8, 4.2, 4.8, 2.2, 3.5, 1.8, 4.5],
        'criticite_geometrie': [0.3, 0.4, 0.5, 0.8, 0.85, 0.7, 0.9, 0.8, 0.6, 0.75, 0.35, 0.9],
        'incidents_recents': [0, 1, 1, 2, 4, 5, 7, 9, 2, 6, 0, 8],
        'presence_travaux': [0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1],
        'meteo_pluie': [0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 1],
        'risque_eleve': [0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1],
    }
    df = pd.DataFrame(data)
    X = df[['trafic_index', 'criticite_geometrie', 'incidents_recents', 'presence_travaux', 'meteo_pluie']]
    y = df['risque_eleve']

    rf = RandomForestClassifier(n_estimators=40, max_depth=5, random_state=42)
    rf.fit(X, y)
    _risk_model_instance = rf
    return _risk_model_instance


def extraire_trafic_secteur(secteur_id: str, street_id: str = "", default_index: float = 2.0) -> float:
    """Récupère l'indice de trafic via ml_congestion (correspondance exacte street_id ou secteur_id)."""
    try:
        from ml_congestion.predictor import predict_congestion_by_street
        now_iso = timezone.now().isoformat()
        predictions = predict_congestion_by_street(simulation_datetime=now_iso)
        if predictions:
            for p in predictions:
                p_street_id = str(p.get('street_id', ''))
                name_low = str(p.get('street_name', '')).lower()
                if (street_id and p_street_id == street_id) or (secteur_id.replace('_', ' ') in name_low) or (secteur_id in p_street_id):
                    return float(p.get('congestion_index', default_index))
            indices = [float(p.get('congestion_index', 2.0)) for p in predictions if 'congestion_index' in p]
            if indices:
                return float(np.mean(indices))
    except Exception:
        pass
    return default_index


def compter_accidents_secteur(lat: float, lng: float, rayon_m: float = 1200, jours: int = 30) -> int:
    """
    Compte le nombre réel d'accidents enregistrés dans le rayon métrique exact du secteur
    lors des `jours` derniers jours (pré-filtre bounding box corrigé en cos(lat) + Haversine).
    """
    try:
        from .models import AlerteAccident
        date_seuil = timezone.now() - timedelta(days=jours)
        delta_lat = rayon_m / 111000.0
        cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
        delta_lng = delta_lat / cos_lat
        qs = AlerteAccident.objects.filter(
            date_creation__gte=date_seuil,
            latitude__gte=lat - delta_lat,
            latitude__lte=lat + delta_lat,
            longitude__gte=lng - delta_lng,
            longitude__lte=lng + delta_lng,
        ).values_list('latitude', 'longitude')
        return sum(1 for a_lat, a_lng in qs if distance_metres(lat, lng, a_lat, a_lng) <= rayon_m)
    except Exception:
        return 0


def evaluer_secteur_region(secteur: dict, meteo_pluie: int = 0, presence_travaux: int = 0) -> dict:
    """
    Calcule le score de risque routier (0 - 100 %) pour un secteur du Cap Bon
    en combinant :
    1. Historique d'accidents réels (35 %)
    2. Criticité géométrique du tronçon (30 %)
    3. Trafic et congestion en direct (35 %)
    """
    lat = secteur["lat"]
    lng = secteur["lng"]
    criticite = float(secteur.get("criticite_geometrie", 0.5))
    rayon = float(secteur.get("rayon_zone_m", 1200))

    # 1. Historique réel des accidents
    nb_accidents = compter_accidents_secteur(lat, lng, rayon_m=rayon, jours=30)
    # 2. Trafic connecté
    trafic_idx = extraire_trafic_secteur(
        secteur["id"],
        street_id=secteur.get("street_id", ""),
        default_index=2.2,
    )

    # 3. Formule composite calibrée (0 à 100%)
    score_accidents = min(35.0, (nb_accidents / 6.0) * 35.0)
    score_geometrie = criticite * 30.0
    score_trafic = ((max(1.0, min(5.0, trafic_idx)) - 1.0) / 4.0) * 35.0

    # Facteurs aggravants : Pluie (+8%), Travaux (+7%)
    bonus_meteo = 8.0 if meteo_pluie == 1 else 0.0
    bonus_travaux = 7.0 if presence_travaux == 1 else 0.0

    score_total = round(min(100.0, max(5.0, score_accidents + score_geometrie + score_trafic + bonus_meteo + bonus_travaux)), 1)

    if score_total >= 70.0:
        couleur = "rouge"
        niveau_libelle = "ÉLEVÉ (ROUGE)"
    elif score_total >= 35.0:
        couleur = "orange"
        niveau_libelle = "MODÉRÉ (ORANGE)"
    else:
        couleur = "vert"
        niveau_libelle = "FAIBLE (VERT)"

    facteurs = []
    if nb_accidents >= 4:
        facteurs.append(f"Historique critique : {nb_accidents} accidents enregistrés (30j)")
    elif nb_accidents >= 2:
        facteurs.append(f"Historique modéré : {nb_accidents} accidents enregistrés (30j)")
    else:
        facteurs.append(f"Faible accidentologie récente ({nb_accidents} accident)")

    if criticite >= 0.75:
        facteurs.append(f"Configuration routière complexe ({secteur.get('type_troncon')})")
    elif criticite >= 0.5:
        facteurs.append(f"Tronçon sensible ({secteur.get('type_troncon')})")

    if trafic_idx >= 3.5:
        facteurs.append(f"Congestion sévère observée (indice {trafic_idx:.1f}/5)")
    elif trafic_idx >= 2.5:
        facteurs.append(f"Trafic dense aux heures de pointe (indice {trafic_idx:.1f}/5)")
    else:
        facteurs.append(f"Trafic fluide (indice {trafic_idx:.1f}/5)")

    if bonus_travaux > 0:
        facteurs.append("Chantier ou rétrécissement de chaussée actif")
    if bonus_meteo > 0:
        facteurs.append("Chaussée glissante suite aux intempéries (Pluie)")

    return {
        "zone_id": secteur["id"],
        "zone_nom": secteur["nom"],
        "delegation": secteur.get("delegation", ""),
        "type_troncon": secteur.get("type_troncon"),
        "latitude": lat,
        "longitude": lng,
        "rayon_zone_m": rayon,
        "score_risque_pourcentage": score_total,
        "niveau_couleur": couleur,
        "niveau_risk_map": niveau_libelle,
        "facteurs_explicatifs": facteurs,
        "details": {
            "accidents_30j": nb_accidents,
            "indice_trafic": round(trafic_idx, 2),
            "criticite_geometrie": criticite,
            "meteo_pluie": meteo_pluie,
            "presence_travaux": presence_travaux,
        },
    }


# Alias de rétro-compatibilité
evaluer_secteur_tunis = evaluer_secteur_region


def prediger_risque_zone(trafic, travaux, pluie, incidents_recents):
    """
    Point d'entrée pour la prédiction dynamique avec paramètres personnalisés (simulateur/modale).
    """
    modele = entrainer_modele_risk_map()
    features = pd.DataFrame(
        [[trafic, 0.7, incidents_recents, travaux, pluie]],
        columns=['trafic_index', 'criticite_geometrie', 'incidents_recents', 'presence_travaux', 'meteo_pluie']
    )
    proba = modele.predict_proba(features)[0][1]

    base_score = float(proba * 60.0)
    add_trafic = (float(trafic) / 5.0) * 20.0
    add_incidents = min(20.0, (float(incidents_recents) / 5.0) * 20.0)
    score = round(min(100.0, max(5.0, base_score + add_trafic + add_incidents)), 1)

    if score >= 70.0:
        niveau = "ELEVE (ROUGE)"
        couleur = "rouge"
    elif score >= 35.0:
        niveau = "MOYEN (ORANGE)"
        couleur = "orange"
    else:
        niveau = "FAIBLE (VERT)"
        couleur = "vert"

    facteurs = []
    if incidents_recents >= 4:
        facteurs.append(f"Historique élevé : {incidents_recents} accidents/30j")
    elif incidents_recents >= 2:
        facteurs.append(f"Historique modéré : {incidents_recents} incidents récents")
    else:
        facteurs.append("Faible fréquence d'incidents récents")

    if trafic >= 3.2:
        facteurs.append(f"Trafic très dense (indice {trafic}/5)")
    elif trafic >= 2.0:
        facteurs.append(f"Circulation modérée (indice {trafic}/5)")

    if travaux == 1:
        facteurs.append("Chantier actif / voie neutralisée")
    if pluie == 1:
        facteurs.append("Intempéries / adhérence réduite (Pluie)")

    return {
        "score_risque_pourcentage": score,
        "niveau_couleur": couleur,
        "niveau_risk_map": niveau,
        "facteurs_explicatifs": facteurs,
    }


def get_toutes_les_zones_risk_map(meteo_pluie: int = 0, presence_travaux: int = 0):
    """Retourne la cartographie complète des secteurs évalués du Cap Bon."""
    return [
        evaluer_secteur_region(s, meteo_pluie=meteo_pluie, presence_travaux=presence_travaux)
        for s in SECTEURS_CAP_BON
    ]
