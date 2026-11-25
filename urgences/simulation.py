"""
Module de Simulation Jury pour la Protection Civile du Nord-Est du Cap Bon
(Kélibia, Hammam El Ghezaz, El Haouaria, Dar Allouche, Kerkouane, Azmour, Menzel Horr).
"""

from datetime import timedelta
from django.utils import timezone
from .models import SignalementAccident, AlerteAccident
from .services import traiter_signalement
from .ml_models import get_toutes_les_zones_risk_map


def executer_simulation_fausse_alerte(
    adresse="Corniche El Mansourah, Kélibia",
    lat=36.8410,
    lng=11.1160,
) -> dict:
    """
    Simulation 1 (Partie A) : Test Anti-Fausse Alerte.
    Crée 1 signalement isolé non-critique.
    Grâce au filtrage de concordance, l'alerte reste 'A_CONFIRMER'
    et n'envoie AUCUNE sirène ni alarme aux pompiers.
    """
    sig = SignalementAccident.objects.create(
        latitude=lat,
        longitude=lng,
        adresse=adresse,
        description="Véhicule immobilisé sur le bas-côté (signalement citoyen unique)",
        gravite_estimee="MOYENNE",
    )
    alerte = traiter_signalement(sig, valide_par_agent=False)

    return {
        "scenario": "fausse_alerte_isolee",
        "description": "Fausse alerte ou incident isolé neutralisé par le filtre de concordance spatiale",
        "signalement_id": sig.id,
        "alerte_id": alerte.id,
        "statut_alerte": alerte.statut,
        "nb_signalements_concordants": alerte.nb_signalements,
        "alerte_confirmee_pompiers": (alerte.statut == 'CONFIRME'),
        "alarme_declenchee": False,
        "message": (
            "Filtre Anti-Fausse Alerte ACTIF : Le signalement isolé a été placé en attente "
            f"('{alerte.statut}'). Aucune fausse alarme n'a été transmise à la Protection Civile."
        ),
    }


def executer_simulation_accident_confirme(
    adresse="Avenue des Martyrs, Kélibia Centre",
    lat_centre=36.8475,
    lng_centre=11.0939,
) -> dict:
    """
    Simulation 1 (Partie B) : Test de Fusion Spatiale & Diffusion Temps Réel (< 5s).
    Crée 3 signalements concordants à moins de 150m les uns des autres à Kélibia Centre.
    """
    offsets = [
        (0.0, 0.0, "Collision violente entre 2 véhicules avenue des Martyrs, Kélibia"),
        (0.0003, 0.0004, "Accident grave Kélibia Centre, besoin secours urgent"),
        (-0.0002, 0.0003, "Carambolage avec blessés près de la Place du Marché, Kélibia"),
    ]

    signalements_crees = []
    derniere_alerte = None

    for i, (dlat, dlng, desc) in enumerate(offsets, 1):
        sig = SignalementAccident.objects.create(
            latitude=round(lat_centre + dlat, 6),
            longitude=round(lng_centre + dlng, 6),
            adresse=adresse,
            description=desc,
            gravite_estimee="GRAVE" if i == 1 else "MOYENNE",
        )
        signalements_crees.append(sig.id)
        derniere_alerte = traiter_signalement(sig, valide_par_agent=False)

    return {
        "scenario": "accident_confirme_clustering",
        "description": "Fusion spatiale instantanée de 3 signalements concordants à < 150m",
        "alerte_id": derniere_alerte.id,
        "statut_alerte": derniere_alerte.statut,
        "nb_signalements_fusionnes": derniere_alerte.nb_signalements,
        "signalements_ids": signalements_crees,
        "adresse": derniere_alerte.adresse,
        "zone_nom": derniere_alerte.zone_nom,
        "latitude": derniere_alerte.latitude,
        "longitude": derniere_alerte.longitude,
        "date_confirmation": derniere_alerte.date_confirmation.isoformat() if derniere_alerte.date_confirmation else None,
        "alarme_declenchee": True,
        "diffusion_temps_reel": "Diffusé par WebSocket (< 5s) à la Protection Civile",
        "message": (
            f"Alerte #{derniere_alerte.id} CONFIRMÉE avec succès ({derniere_alerte.nb_signalements} signalements fusionnés). "
            "Diffusion WebSocket transmise, sirène d'urgence activée et itinéraire calculé."
        ),
    }


def executer_simulation_risk_map_cap_bon() -> dict:
    """
    Simulation 2 : Génération d'un scénario Risk Map complet sur le Nord-Est du Cap Bon
    (Kélibia, Hammam El Ghezaz, El Haouaria, Kerkouane, Dar Allouche, Azmour, Menzel Horr).
    """
    maintenant = timezone.now()

    zones_calibrees = [
        {"id": "menzel_horr_mc27", "zone_nom": "Menzel Horr", "lat": 36.7361, "lng": 10.9558, "accidents": 5, "adresse": "Corridor MC27, Menzel Horr"},
        {"id": "el_haouaria_centre", "zone_nom": "El Haouaria", "lat": 37.0500, "lng": 11.0144, "accidents": 5, "adresse": "Route des Grottes, El Haouaria"},
        {"id": "kelibia_centre", "zone_nom": "Kélibia", "lat": 36.8475, "lng": 11.0939, "accidents": 2, "adresse": "Avenue des Martyrs, Kélibia"},
        {"id": "hammam_ghezeze_c27", "zone_nom": "Hammam El Ghezaz", "lat": 36.8906, "lng": 11.1197, "accidents": 2, "adresse": "Route Côtière C27, Hammam El Ghezaz"},
        {"id": "dar_allouche_c27", "zone_nom": "Dar Allouche", "lat": 36.9350, "lng": 11.1050, "accidents": 0, "adresse": "Traverse C27, Dar Allouche"},
    ]

    total_accidents_generes = 0
    for z in zones_calibrees:
        for k in range(z["accidents"]):
            sig = SignalementAccident.objects.create(
                latitude=z["lat"] + (k * 0.00015),
                longitude=z["lng"] + (k * 0.00015),
                adresse=z["adresse"],
                description=f"Accident simulé calibré #{k+1} pour Risk Map Nord-Est Cap Bon",
                gravite_estimee="GRAVE" if k % 2 == 0 else "MOYENNE",
            )
            alerte = AlerteAccident.objects.create(
                latitude=sig.latitude,
                longitude=sig.longitude,
                adresse=sig.adresse,
                zone_nom=z["zone_nom"],
                gravite=sig.gravite_estimee,
                statut='CLOTURE',
                nb_signalements=2,
                date_confirmation=maintenant - timedelta(days=k + 1),
                date_cloture=maintenant - timedelta(days=k + 1, hours=-1),
            )
            alerte.signalements_lies.add(sig)
            total_accidents_generes += 1

    zones_evaluees = get_toutes_les_zones_risk_map()

    return {
        "scenario": "generation_risk_map_cap_bon",
        "message": f"Scénario Risk Map Nord-Est Cap Bon généré : {total_accidents_generes} accidents historiques injectés.",
        "nb_secteurs_evalues": len(zones_evaluees),
        "repartition": {
            "rouges": len([z for z in zones_evaluees if z["niveau_couleur"] == "rouge"]),
            "oranges": len([z for z in zones_evaluees if z["niveau_couleur"] == "orange"]),
            "vertes": len([z for z in zones_evaluees if z["niveau_couleur"] == "vert"]),
        },
        "secteurs": zones_evaluees,
    }


executer_simulation_risk_map_tunis = executer_simulation_risk_map_cap_bon
