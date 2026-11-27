"""
Moteur Prédictif Risk Map (0 - 100 %) pour la Protection Civile du Cap Bon.
Combine :
1. L'historique des accidents enregistrés dans la zone (base de données réelle + distance Haversine).
2. La géométrie / criticité du tronçon (échangeur, carrefour giratoire, axe régional).
3. Le niveau de trafic / congestion (interconnecté avec le module ml_congestion).
"""

from datetime import timedelta
import math
import requests
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from django.core.cache import cache
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


def _fetch_simulator_segments() -> list:
    """Récupère les tronçons en direct du simulateur de trafic (port 8001) avec cache 5s."""
    cached = cache.get("sim_live_segments")
    if cached is not None:
        return cached
    try:
        resp = requests.get("http://127.0.0.1:8001/api/traffic/segments", timeout=0.8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                cache.set("sim_live_segments", data, timeout=5)
                return data
    except Exception:
        pass
    return []


def extraire_trafic_secteur(
    secteur_id: str,
    street_id: str = "",
    default_index: float = 2.0,
    lat: float | None = None,
    lng: float | None = None,
) -> float:
    """
    Récupère l'indice de trafic en direct depuis le simulateur (port 8001) en priorité,
    avec fallback sur ml_congestion.
    """
    # 1. Priorité au simulateur de trafic en direct (synchronisé avec la carte)
    sim_segments = _fetch_simulator_segments()
    if sim_segments:
        # Correspondance par street_id exact ou nom/zone
        matched_indices = []
        sec_tokens = [t for t in secteur_id.lower().split("_") if len(t) > 2]
        for seg in sim_segments:
            seg_id = str(seg.get("id", "")).lower()
            seg_name = str(seg.get("name", "")).lower()
            seg_zone = str(seg.get("zone", "")).lower()
            if (street_id and seg_id == street_id.lower()) or any(
                tok in seg_id or tok in seg_name or tok in seg_zone for tok in sec_tokens
            ):
                matched_indices.append(float(seg.get("congestion_index", default_index)))
            elif lat is not None and lng is not None and seg.get("coordinates"):
                # Correspondance par proximité géographique (<= 2.5 km)
                coords = seg["coordinates"]
                if any(distance_metres(lat, lng, pt[0], pt[1]) <= 2500.0 for pt in coords):
                    matched_indices.append(float(seg.get("congestion_index", default_index)))

        if matched_indices:
            # Prend le maximum observé dans le secteur pour refléter les points rouges
            return float(max(matched_indices))

        all_indices = [float(s.get("congestion_index", default_index)) for s in sim_segments]
        if all_indices:
            return float(np.mean(all_indices))

    # 2. Fallback sur le modèle ML ml_congestion si le simulateur est hors ligne
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


def compter_chantiers_secteur(lat: float, lng: float, street_id: str = "", rayon_m: float = 1500.0) -> dict:
    """
    Compte les chantiers actifs (EN_COURS) dans le secteur (par corridor street_id ou rayon GPS).
    """
    try:
        from .models import Chantier
        qs = Chantier.objects.filter(statut='EN_COURS')
        matched = []
        for ch in qs:
            same_street = bool(street_id and ch.street_id and ch.street_id == street_id)
            in_radius = distance_metres(lat, lng, ch.latitude, ch.longitude) <= max(rayon_m, 1500.0)
            if same_street or in_radius:
                matched.append(ch)
        return {
            "count": len(matched),
            "voies_bloquees": sum(c.voies_bloquees for c in matched),
            "has_critique": any(c.priorite == 'CRITIQUE' for c in matched),
            "has_elevee": any(c.priorite == 'ELEVEE' for c in matched),
            "titres": [c.titre for c in matched[:2]],
        }
    except Exception:
        return {"count": 0, "voies_bloquees": 0, "has_critique": False, "has_elevee": False, "titres": []}


def evaluer_secteur_region(secteur: dict, meteo_pluie: int = 0, presence_travaux: int = 0) -> dict:
    """
    Calcule le score de risque routier (0 - 100 %) pour un secteur du Cap Bon
    en combinant :
    1. Historique d'accidents réels (35 %)
    2. Criticité géométrique du tronçon (30 %)
    3. Trafic et congestion en direct (35 %)
    + Impact réel des chantiers déclarés en base (Chantier) et météo.
    """
    lat = secteur["lat"]
    lng = secteur["lng"]
    criticite = float(secteur.get("criticite_geometrie", 0.5))
    rayon = float(secteur.get("rayon_zone_m", 1200))

    # 1. Historique réel des accidents
    nb_accidents = compter_accidents_secteur(lat, lng, rayon_m=rayon, jours=30)
    # 2. Chantiers actifs dans le secteur
    chantiers_info = compter_chantiers_secteur(
        lat,
        lng,
        street_id=secteur.get("street_id", ""),
        rayon_m=rayon,
    )
    nb_chantiers = chantiers_info["count"]
    travaux_effectifs = 1 if (presence_travaux == 1 or nb_chantiers > 0) else 0

    # 3. Trafic connecté (simulateur en direct + fallback ML)
    trafic_idx = extraire_trafic_secteur(
        secteur["id"],
        street_id=secteur.get("street_id", ""),
        default_index=2.2,
        lat=lat,
        lng=lng,
    )

    # 4. Formule composite calibrée (0 à 100%)
    score_accidents = min(35.0, (nb_accidents / 6.0) * 35.0)
    score_geometrie = criticite * 30.0
    score_trafic = ((max(1.0, min(5.0, trafic_idx)) - 1.0) / 4.0) * 35.0

    # Facteurs aggravants : Pluie (+8%), Travaux manuels (+7%) ou Chantiers déclarés (+15% à +28%)
    bonus_meteo = 8.0 if meteo_pluie == 1 else 0.0
    if nb_chantiers > 0:
        bonus_travaux = 15.0 + min(8.0, chantiers_info["voies_bloquees"] * 3.0)
        if chantiers_info["has_critique"]:
            bonus_travaux += 7.0
        elif chantiers_info["has_elevee"]:
            bonus_travaux += 4.0
    elif presence_travaux == 1:
        bonus_travaux = 7.0
    else:
        bonus_travaux = 0.0

    # Facteur aggravant trafic critique en direct (saturation / paralysie simulateur)
    if trafic_idx >= 4.5:
        bonus_saturation = 18.0
    elif trafic_idx >= 3.8:
        bonus_saturation = 10.0
    else:
        bonus_saturation = 0.0

    score_total = round(min(100.0, max(5.0, score_accidents + score_geometrie + score_trafic + bonus_meteo + bonus_travaux + bonus_saturation)), 1)

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

    if nb_chantiers > 0:
        titres_str = ", ".join(chantiers_info["titres"])
        facteurs.append(
            f"🚧 {nb_chantiers} chantier(s) actif(s) ({chantiers_info['voies_bloquees']} voie(s) bloquée(s) : {titres_str})"
        )
    elif bonus_travaux > 0:
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
            "presence_travaux": travaux_effectifs,
            "chantiers_actifs": nb_chantiers,
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
