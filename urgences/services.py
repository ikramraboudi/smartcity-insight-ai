import math
import threading
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from config.geo_config import DELEGATIONS_CAP_BON, WS_GROUP_NAME
from .models import SignalementAccident, AlerteAccident, JournalAudit, JournalAuditIntervention

# Paramètres configurables du regroupement spatial et temporel
RAYON_PROXIMITE_METRES = getattr(settings, 'URGENCES_RAYON_PROXIMITE_METRES', 250)
FENETRE_TEMPORELLE_MINUTES = getattr(settings, 'URGENCES_FENETRE_TEMPORELLE_MINUTES', 15)
SEUIL_CONFIRMATION_CONCORDANCE = getattr(settings, 'URGENCES_SEUIL_CONFIRMATION', 2)


def inferer_delegation_proche(lat: float, lon: float) -> str:
    """Identifie la délégation du Cap Bon la plus proche des coordonnées GPS."""
    if not DELEGATIONS_CAP_BON:
        return ""
    nearest = min(
        DELEGATIONS_CAP_BON,
        key=lambda d: distance_metres(lat, lon, d["lat"], d["lng"]),
    )
    return nearest["nom"]

def distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance géodésique précise (formule de Haversine) entre deux points GPS en mètres.
    Fonctionne de manière transparente sous PostGIS, PostgreSQL et SQLite.
    """
    R = 6371000.0  # Rayon moyen de la Terre en mètres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

def trouver_alerte_proche(lat: float, lon: float, rayon_metres: float = RAYON_PROXIMITE_METRES):
    """
    Recherche une alerte active existante dans le rayon géographique configurable
    et dans la fenêtre temporelle de 15 minutes, avec pré-filtrage bounding box SQL.
    """
    fenetre_temps = timezone.now() - timedelta(minutes=FENETRE_TEMPORELLE_MINUTES)
    delta_lat = (rayon_metres / 111000.0) * 1.5
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    delta_lon = delta_lat / cos_lat

    alertes_actives = (
        AlerteAccident.objects.filter(
            date_creation__gte=fenetre_temps,
            latitude__gte=lat - delta_lat,
            latitude__lte=lat + delta_lat,
            longitude__gte=lon - delta_lon,
            longitude__lte=lon + delta_lon,
        )
        .exclude(statut='CLOTURE')
    )

    # Filtrage exact par distance géodésique Haversine
    for alerte in alertes_actives:
        if distance_metres(lat, lon, alerte.latitude, alerte.longitude) <= rayon_metres:
            return alerte
    return None

def traiter_signalement(
    signalement: SignalementAccident,
    valide_par_agent: bool = False,
    rayon_metres: float = RAYON_PROXIMITE_METRES
) -> AlerteAccident:
    """
    Logique de Qualification & Clustering PostGIS :
    1. Regroupe les signalements concordants dans un rayon configurable (200 m) et 15 min.
    2. Filtrage strict anti-fausses alertes :
       - 1 signalement isolé non-critique reste au statut 'A_CONFIRMER' (pas de sirène pompiers).
       - Dès qu'au moins 2 signalements concordants sont reçus (ou gravité GRAVE/CRITIQUE, ou validation agent),
         l'alerte est CONFIRMÉE et transmise instantanément (< 5s) à la Protection Civile.
    """
    alerte_proche = trouver_alerte_proche(signalement.latitude, signalement.longitude, rayon_metres)

    est_nouveau = False
    if alerte_proche:
        alerte_proche.signalements_lies.add(signalement)
        alerte_proche.nb_signalements = alerte_proche.signalements_lies.count()
        # Si le nouveau signalement a une gravité plus élevée, mettre à jour la gravité de l'alerte
        if signalement.gravite_estimee in ('GRAVE', 'CRITIQUE'):
            alerte_proche.gravite = 'GRAVE'
    else:
        alerte_proche = AlerteAccident.objects.create(
            latitude=signalement.latitude,
            longitude=signalement.longitude,
            adresse=signalement.adresse or f"GPS ({signalement.latitude:.4f}, {signalement.longitude:.4f})",
            zone_nom=inferer_delegation_proche(signalement.latitude, signalement.longitude),
            gravite='GRAVE' if signalement.gravite_estimee in ('GRAVE', 'CRITIQUE') else signalement.gravite_estimee,
            statut='A_CONFIRMER',
            nb_signalements=1
        )
        alerte_proche.signalements_lies.add(signalement)
        est_nouveau = True

    # Détection de la condition de confirmation
    gravite_critique = (
        signalement.gravite_estimee in ('GRAVE', 'CRITIQUE')
        or alerte_proche.gravite in ('GRAVE', 'CRITIQUE')
    )
    concordance_suffisante = alerte_proche.nb_signalements >= SEUIL_CONFIRMATION_CONCORDANCE
    doit_confirmer = concordance_suffisante or gravite_critique or valide_par_agent

    if alerte_proche.statut == 'A_CONFIRMER' and doit_confirmer:
        statut_prec = alerte_proche.statut
        alerte_proche.statut = 'CONFIRME'
        alerte_proche.date_confirmation = timezone.now()
        alerte_proche.save()

        # Audit standard & Audit strict d'intervention
        motif = (
            f"Concordance établie ({alerte_proche.nb_signalements} signalements à < {rayon_metres}m)"
            if concordance_suffisante else
            ("Gravité critique détectée" if gravite_critique else "Validation par opérateur")
        )
        JournalAudit.objects.create(
            alerte=alerte_proche,
            action=f"Alerte CONFIRMEE : {motif}"
        )
        JournalAuditIntervention.objects.create(
            alerte=alerte_proche,
            statut_precedent=statut_prec,
            nouveau_statut='CONFIRME',
            note_intervention=f"Confirmation automatique : {motif}"
        )

        # Diffusion temps réel immédiate (< 5s)
        diffuser_alerte_temps_reel(alerte_proche)
    else:
        alerte_proche.save()
        if est_nouveau:
            JournalAudit.objects.create(
                alerte=alerte_proche,
                action=f"Alerte créée en attente de confirmation ({alerte_proche.nb_signalements} sig.)"
            )

    return alerte_proche

def enregistrer_changement_statut(
    alerte: AlerteAccident,
    nouveau_statut: str,
    intervenant=None,
    matricule: str = '',
    note: str = ''
) -> AlerteAccident:
    """
    Applique le changement d'état du workflow strict :
    'CONFIRME' -> 'PRISE_EN_CHARGE' -> 'EN_INTERVENTION' -> 'CLOTURE'
    avec horodatage exact, création de l'entrée JournalAuditIntervention et diffusion WebSocket.
    """
    statut_precedent = alerte.statut
    now = timezone.now()

    alerte.statut = nouveau_statut
    if nouveau_statut == 'CONFIRME' and not alerte.date_confirmation:
        alerte.date_confirmation = now
    elif nouveau_statut == 'PRISE_EN_CHARGE':
        alerte.date_prise_en_charge = now
    elif nouveau_statut == 'EN_INTERVENTION':
        alerte.date_en_intervention = now
    elif nouveau_statut == 'CLOTURE':
        alerte.date_cloture = now

    alerte.save()

    # Création de l'entrée dans le JournalAuditIntervention
    JournalAuditIntervention.objects.create(
        alerte=alerte,
        intervenant=intervenant if (intervenant and getattr(intervenant, 'is_authenticated', False)) else None,
        matricule_intervenant=matricule or (getattr(intervenant, 'username', '') if intervenant else ''),
        statut_precedent=statut_precedent,
        nouveau_statut=nouveau_statut,
        note_intervention=note
    )

    # Création également de l'audit simple pour la compatibilité
    JournalAudit.objects.create(
        alerte=alerte,
        utilisateur=intervenant if (intervenant and getattr(intervenant, 'is_authenticated', False)) else None,
        action=f"Statut modifié : {statut_precedent} -> {nouveau_statut} {('('+note+')') if note else ''}"
    )

    # Diffusion en direct de la mise à jour à tous les écrans connectés
    diffuser_changement_statut(alerte)
    return alerte

def diffuser_alerte_temps_reel(alerte: AlerteAccident):
    """Diffuse l'alerte confirmée sur le groupe WebSocket de la Protection Civile (< 5s)."""
    alerte_data = {
        "id": alerte.id,
        "statut": alerte.statut,
        "gravite": alerte.gravite,
        "adresse": alerte.adresse,
        "zone_nom": alerte.zone_nom,
        "latitude": alerte.latitude,
        "longitude": alerte.longitude,
        "nb_signalements": alerte.nb_signalements,
        "date_creation": alerte.date_creation.isoformat() if alerte.date_creation else None,
        "date_confirmation": alerte.date_confirmation.isoformat() if alerte.date_confirmation else None,
    }

    def _do_send():
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    WS_GROUP_NAME,
                    {
                        "type": "envoyer_alerte",
                        "data": alerte_data
                    }
                )
        except Exception:
            pass

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()
    t.join(timeout=0.3)

def diffuser_changement_statut(alerte: AlerteAccident):
    """Diffuse le changement de statut d'intervention par WebSocket."""
    alerte_data = {
        "id": alerte.id,
        "statut": alerte.statut,
        "gravite": alerte.gravite,
        "adresse": alerte.adresse,
        "latitude": alerte.latitude,
        "longitude": alerte.longitude,
        "date_prise_en_charge": alerte.date_prise_en_charge.isoformat() if alerte.date_prise_en_charge else None,
        "date_en_intervention": alerte.date_en_intervention.isoformat() if alerte.date_en_intervention else None,
        "date_cloture": alerte.date_cloture.isoformat() if alerte.date_cloture else None,
    }

    def _do_send():
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    WS_GROUP_NAME,
                    {
                        "type": "mise_a_jour_statut",
                        "data": alerte_data
                    }
                )
        except Exception:
            pass

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()
    t.join(timeout=0.3)
