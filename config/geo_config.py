"""
Configuration géographique centralisée de SmartCity Insight AI.
Portée territoriale active : Nord-Est du Cap Bon
(Kélibia, Hammam El Ghezaz, El Haouaria, Dar Allouche, Kerkouane, Azmour, Menzel Horr).

Ce module constitue la source unique de vérité pour :
- Le centre, le zoom et les limites (bounding box) des cartes
- La liste des communes / localités du Nord-Est du Cap Bon
- Les casernes de Protection Civile de la zone
- Les secteurs stratégiques de la Risk Map et les points de simulation
- Les paramètres spatiaux locaux (clustering, dispersion, groupe WebSocket)
"""

import os
from typing import Any, Dict, List

REGION_ID = os.environ.get("SMARTCITY_REGION_ID", "cap_bon_ne")
REGION_NAME = os.environ.get(
    "SMARTCITY_REGION_NAME",
    "Nord-Est Cap Bon (Kélibia • Hammam El Ghezaz • El Haouaria)",
)
REGION_SHORT_NAME = os.environ.get("SMARTCITY_REGION_SHORT_NAME", "Kélibia / Cap Bon NE")
DEFAULT_CITY = os.environ.get("SMARTCITY_DEFAULT_CITY", "Kélibia")
DEFAULT_ADDRESS = os.environ.get("SMARTCITY_DEFAULT_ADDRESS", "Avenue des Martyrs, Kélibia")

# Coordonnées par défaut (Kélibia Centre)
DEFAULT_COORDS: Dict[str, float] = {
    "latitude": 36.8475,
    "longitude": 11.0939,
}

# Paramètres de cadrage cartographique (Nord-Est Cap Bon)
MAP_CONFIG: Dict[str, Any] = {
    "center": [36.935, 11.055],
    "default_point": [36.8475, 11.0939],
    "zoom": 12,
    "picker_zoom": 13,
    "min_zoom": 11,
    "max_zoom": 18,
    "bounds": {
        "south_west": [36.80, 10.94],
        "north_east": [37.09, 11.15],
    },
}

# Groupe Django Channels WebSocket pour la salle de commandement Kélibia / Cap Bon NE
WS_GROUP_NAME = os.environ.get("SMARTCITY_WS_GROUP", "protection_civile_kelibia_ne")

# Paramètres spatiaux adaptés au sous-bassin Nord-Est du Cap Bon
SPATIAL_CONFIG: Dict[str, Any] = {
    "urgences_rayon_proximite_metres": int(os.environ.get("URGENCES_RAYON_PROXIMITE_METRES", 200)),
    "urgences_fenetre_minutes": int(os.environ.get("URGENCES_FENETRE_TEMPORELLE_MINUTES", 15)),
    "urgences_seuil_confirmation": int(os.environ.get("URGENCES_SEUIL_CONFIRMATION", 2)),
    "doublon_rayon_metres": 50.0,
    "doublon_fenetre_minutes": 10,
    "grid_step_deg": 0.0045,  # ~500 m
    "max_hotspots_zones": 12,
    "anomaly_spatial_scale_m": 250.0,
}

# Communes et localités du Nord-Est du Cap Bon
LOCALITES_CAP_BON_NE: List[Dict[str, Any]] = [
    {"id": "kelibia", "nom": "Kélibia", "code_postal": "8090", "lat": 36.8475, "lng": 11.0939},
    {"id": "hammam_ghezeze", "nom": "Hammam El Ghezaz", "code_postal": "8025", "lat": 36.8906, "lng": 11.1197},
    {"id": "el_haouaria", "nom": "El Haouaria", "code_postal": "8045", "lat": 37.0500, "lng": 11.0144},
    {"id": "dar_allouche", "nom": "Dar Allouche", "code_postal": "8055", "lat": 36.9350, "lng": 11.1050},
    {"id": "kerkouane", "nom": "Kerkouane", "code_postal": "8045", "lat": 36.9467, "lng": 11.0989},
    {"id": "azmour", "nom": "Azmour", "code_postal": "8035", "lat": 36.8260, "lng": 11.0180},
    {"id": "menzel_horr", "nom": "Menzel Horr", "code_postal": "8015", "lat": 36.7361, "lng": 10.9558},
]

# Alias conservés pour les imports existants
DELEGATIONS_CAP_BON = LOCALITES_CAP_BON_NE
DELEGATION_NAMES: List[str] = [d["nom"] for d in LOCALITES_CAP_BON_NE]

CIRCONSCRIPTIONS_PRESETS: List[str] = [
    f"Commune {d['nom']} ({d['code_postal']})" for d in LOCALITES_CAP_BON_NE
]

# Casernes et unités de la Protection Civile (Nord-Est du Cap Bon)
# Azmour, Hammam Ghezaz et Menzel Horr ne disposent pas de caserne propre :
# Kélibia, Azmour et Hammam Ghezaz sont directement desservies par la caserne de Kélibia.
CASERNES_CAP_BON: List[Dict[str, Any]] = [
    {
        "id": "caserne-kelibia",
        "nom": "Protection Civile Kélibia",
        "adresse": "Avenue des Martyrs / Avenue de l'Environnement, 8090 Kélibia",
        "delegation": "Kélibia",
        "communes_desservies": ["Kélibia", "Azmour", "Hammam Ghezaz"],
        "latitude": 36.8475,
        "longitude": 11.0939,
        "telephone": "198 / 72 296 366",
        "ambulances_disponibles": 3,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE",
    },
    {
        "id": "caserne-el-haouaria",
        "nom": "Protection civile El Haouaria",
        "adresse": "Croisement des routes MC 26 et MC 27, 8045 El Haouaria",
        "delegation": "El Haouaria",
        "communes_desservies": ["El Haouaria"],
        "latitude": 37.0500,
        "longitude": 11.0144,
        "telephone": "198 / 72 269 575",
        "ambulances_disponibles": 2,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE",
    },
]

LOCALITES_SANS_CASERNE: List[str] = [
    "Azmour (desservie par Protection Civile Kélibia)",
    "Hammam Ghezaz (desservie par Protection Civile Kélibia)",
    "Menzel Horr (sans caserne dédiée)",
]

# Secteurs stratégiques Risk Map du Nord-Est Cap Bon (alignés avec ml_congestion)
SECTEURS_CAP_BON: List[Dict[str, Any]] = [
    {
        "id": "kelibia_centre",
        "street_id": "seg_kelibia_centre",
        "nom": "Kélibia Centre (Avenue des Martyrs & Place du Marché)",
        "delegation": "Kélibia",
        "lat": 36.8475,
        "lng": 11.0939,
        "type_troncon": "Artère urbaine centrale à forte densité piétonne",
        "criticite_geometrie": 0.70,
        "vitesse_reference_kmh": 45,
        "rayon_zone_m": 600,
    },
    {
        "id": "kelibia_port_mansourah",
        "street_id": "seg_kelibia_port_mansourah",
        "nom": "Port de Kélibia & Corniche El Mansourah",
        "delegation": "Kélibia",
        "lat": 36.8410,
        "lng": 11.1160,
        "type_troncon": "Axe portuaire et littoral touristique",
        "criticite_geometrie": 0.65,
        "vitesse_reference_kmh": 50,
        "rayon_zone_m": 650,
    },
    {
        "id": "hammam_ghezeze_c27",
        "street_id": "seg_hammam_ghezeze_c27",
        "nom": "Hammam El Ghezaz — Route Côtière C27 & Zone Balnéaire",
        "delegation": "Hammam El Ghezaz",
        "lat": 36.8906,
        "lng": 11.1197,
        "type_troncon": "Carrefour littoral et accès plages",
        "criticite_geometrie": 0.60,
        "vitesse_reference_kmh": 55,
        "rayon_zone_m": 700,
    },
    {
        "id": "dar_allouche_c27",
        "street_id": "seg_dar_allouche_c27",
        "nom": "Dar Allouche — Traverse C27 Nord",
        "delegation": "Dar Allouche",
        "lat": 36.9350,
        "lng": 11.1050,
        "type_troncon": "Traverse rurale à circulation agricole et touristique",
        "criticite_geometrie": 0.55,
        "vitesse_reference_kmh": 60,
        "rayon_zone_m": 800,
    },
    {
        "id": "kerkouane_littoral",
        "street_id": "seg_kerkouane_littoral",
        "nom": "Kerkouane — Route Côtière & Site Archéologique",
        "delegation": "Kerkouane",
        "lat": 36.9467,
        "lng": 11.0989,
        "type_troncon": "Route côtière sinueuse à visibilité réduite",
        "criticite_geometrie": 0.72,
        "vitesse_reference_kmh": 60,
        "rayon_zone_m": 900,
    },
    {
        "id": "el_haouaria_centre",
        "street_id": "seg_el_haouaria_centre",
        "nom": "El Haouaria — Centre-Ville & Route des Grottes",
        "delegation": "El Haouaria",
        "lat": 37.0500,
        "lng": 11.0144,
        "type_troncon": "Extrémité nord du Cap Bon exposée au vent marin",
        "criticite_geometrie": 0.78,
        "vitesse_reference_kmh": 50,
        "rayon_zone_m": 800,
    },
    {
        "id": "azmour_carrefour",
        "street_id": "seg_azmour_carrefour",
        "nom": "Azmour — Carrefour Kélibia Ouest / Route de Takelsa",
        "delegation": "Azmour",
        "lat": 36.8260,
        "lng": 11.0180,
        "type_troncon": "Intersection interurbaine à flux agricoles",
        "criticite_geometrie": 0.68,
        "vitesse_reference_kmh": 70,
        "rayon_zone_m": 800,
    },
    {
        "id": "menzel_horr_mc27",
        "street_id": "seg_menzel_horr_mc27",
        "nom": "Menzel Horr — Corridor MC27 (Entrée Sud Kélibia)",
        "delegation": "Menzel Horr",
        "lat": 36.7361,
        "lng": 10.9558,
        "type_troncon": "Route régionale MC27 à double sens et poids-lourds",
        "criticite_geometrie": 0.80,
        "vitesse_reference_kmh": 75,
        "rayon_zone_m": 900,
    },
]

# Points de simulation d'accidents réalistes dans le Nord-Est du Cap Bon
POINTS_SIMULATION_CAP_BON: List[Dict[str, Any]] = [
    {"adresse": "Avenue des Martyrs, Kélibia Centre", "zone_nom": "Kélibia", "lat": 36.8475, "lng": 11.0939, "gravite": "GRAVE"},
    {"adresse": "Zone du Port / Route d'El Mansourah, Kélibia", "zone_nom": "Kélibia", "lat": 36.8410, "lng": 11.1160, "gravite": "MOYENNE"},
    {"adresse": "Route Côtière C27, Hammam El Ghezaz", "zone_nom": "Hammam El Ghezaz", "lat": 36.8906, "lng": 11.1197, "gravite": "GRAVE"},
    {"adresse": "Traverse C27, Dar Allouche", "zone_nom": "Dar Allouche", "lat": 36.9350, "lng": 11.1050, "gravite": "MOYENNE"},
    {"adresse": "Route du Site Archéologique, Kerkouane", "zone_nom": "Kerkouane", "lat": 36.9467, "lng": 11.0989, "gravite": "GRAVE"},
    {"adresse": "Entrée Sud / Route des Grottes, El Haouaria", "zone_nom": "El Haouaria", "lat": 37.0500, "lng": 11.0144, "gravite": "GRAVE"},
    {"adresse": "Carrefour Azmour, Route de Kélibia Ouest", "zone_nom": "Azmour", "lat": 36.8260, "lng": 11.0180, "gravite": "MOYENNE"},
    {"adresse": "Corridor MC27, Traverse Menzel Horr", "zone_nom": "Menzel Horr", "lat": 36.7361, "lng": 10.9558, "gravite": "GRAVE"},
]


def get_public_geo_config() -> Dict[str, Any]:
    """Retourne le bloc de configuration géographique public pour le frontend React."""
    return {
        "region_id": REGION_ID,
        "region_name": REGION_NAME,
        "region_short_name": REGION_SHORT_NAME,
        "default_city": DEFAULT_CITY,
        "default_address": DEFAULT_ADDRESS,
        "default_coords": DEFAULT_COORDS,
        "map": MAP_CONFIG,
        "delegations": LOCALITES_CAP_BON_NE,
        "delegation_names": DELEGATION_NAMES,
        "circonscriptions": CIRCONSCRIPTIONS_PRESETS,
    }
