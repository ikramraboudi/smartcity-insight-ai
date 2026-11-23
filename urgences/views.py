import random
import threading
import json
import urllib.request
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import SignalementAccident, AlerteAccident, JournalAudit, JournalAuditIntervention
from .services import (
    traiter_signalement,
    diffuser_alerte_temps_reel,
    enregistrer_changement_statut,
)
from .ml_models import (
    prediger_risque_zone,
    get_toutes_les_zones_risk_map,
    SECTEURS_TUNIS,
)
from .llm_assistant import interroger_assistant_llm
from .simulation import (
    executer_simulation_fausse_alerte,
    executer_simulation_accident_confirme,
    executer_simulation_risk_map_tunis,
)

def notifier_simulateur_accident(alerte):
    """Notifie le simulateur de trafic en tâche de fond pour provoquer un bouchon."""
    def _worker():
        try:
            payload = json.dumps({
                "alerte_id": alerte.id,
                "latitude": float(alerte.latitude),
                "longitude": float(alerte.longitude),
                "gravite": str(alerte.gravite),
                "description": f"Accident {alerte.adresse}"
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8001/api/traffic/events/accident",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=1.5)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def notifier_simulateur_cloture(alerte_id):
    """Notifie le simulateur de trafic pour rétablir la fluidité."""
    def _worker():
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:8001/api/traffic/events/clear?alerte_id={alerte_id}",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=1.5)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

CASERNES_TUNIS = [
    {
        "id": "caserne-bab-el-khadra",
        "nom": "Caserne Centrale - Bab El Khadra",
        "adresse": "Avenue Habib Thameur / Bab El Khadra, Tunis",
        "latitude": 36.8123,
        "longitude": 10.1784,
        "telephone": "198 / +216 71 345 678",
        "ambulances_disponibles": 3,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE"
    },
    {
        "id": "caserne-bab-saadoun",
        "nom": "Caserne Médina Ouest - Bab Saadoun",
        "adresse": "Place Bab Saadoun, Tunis",
        "latitude": 36.8095,
        "longitude": 10.1582,
        "telephone": "198 / +216 71 560 123",
        "ambulances_disponibles": 2,
        "camions_disponibles": 1,
        "statut": "OPERATIONNELLE"
    },
    {
        "id": "caserne-montplaisir",
        "nom": "Caserne Lac & Montplaisir",
        "adresse": "Avenue du Japon, Montplaisir, Tunis",
        "latitude": 36.8248,
        "longitude": 10.1906,
        "telephone": "198 / +216 71 840 990",
        "ambulances_disponibles": 4,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE"
    },
    {
        "id": "caserne-goulette",
        "nom": "Caserne Port & Banlieue Nord - La Goulette",
        "adresse": "Avenue Franklin Roosevelt, La Goulette",
        "latitude": 36.8182,
        "longitude": 10.3045,
        "telephone": "198 / +216 71 735 000",
        "ambulances_disponibles": 2,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE"
    },
    {
        "id": "caserne-ariana",
        "nom": "Caserne Ariana Centre",
        "adresse": "Avenue Taïeb Mhiri, Ariana",
        "latitude": 36.8625,
        "longitude": 10.1956,
        "telephone": "198 / +216 71 710 400",
        "ambulances_disponibles": 3,
        "camions_disponibles": 2,
        "statut": "OPERATIONNELLE"
    }
]

POINTS_SIMULATION = [
    {"adresse": "Avenue Habib Bourguiba, Tunis Centre", "lat": 36.8002, "lng": 10.1865, "gravite": "GRAVE"},
    {"adresse": "Échangeur Bab Alioua, Sortie Sud", "lat": 36.7865, "lng": 10.1832, "gravite": "GRAVE"},
    {"adresse": "Avenue Mohamed V, devant Cité de la Culture", "lat": 36.8142, "lng": 10.1824, "gravite": "MOYENNE"},
    {"adresse": "Route X / Bardo - Rond-Point", "lat": 36.8115, "lng": 10.1384, "gravite": "GRAVE"},
    {"adresse": "Les Berges du Lac 1 - Rue du Lac Windermere", "lat": 36.8340, "lng": 10.2330, "gravite": "MOYENNE"},
    {"adresse": "Route de la Marsa (RN9) - Échangeur Ain Zaghouan", "lat": 36.8524, "lng": 10.2785, "gravite": "GRAVE"},
    {"adresse": "Avenue de Carthage, Tunis", "lat": 36.7954, "lng": 10.1820, "gravite": "FAIBLE"},
    {"adresse": "Route de Bizerte (GP8), Ariana Ouest", "lat": 36.8600, "lng": 10.1650, "gravite": "GRAVE"},
]

@api_view(['GET'])
def lister_alertes(request):
    """Retourne la liste des alertes d'accident récentes"""
    alertes = AlerteAccident.objects.all().order_by('-date_creation')[:50]
    data = []
    for a in alertes:
        data.append({
            "id": a.id,
            "statut": a.statut,
            "gravite": a.gravite,
            "adresse": a.adresse,
            "zone_nom": a.zone_nom,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "nb_signalements": a.nb_signalements,
            "date_creation": a.date_creation.isoformat() if a.date_creation else None,
            "date_confirmation": a.date_confirmation.isoformat() if a.date_confirmation else None,
            "date_prise_en_charge": a.date_prise_en_charge.isoformat() if a.date_prise_en_charge else None,
            "date_en_intervention": a.date_en_intervention.isoformat() if a.date_en_intervention else None,
            "date_cloture": a.date_cloture.isoformat() if a.date_cloture else None,
        })
    return Response(data)

@api_view(['GET'])
def lister_casernes(request):
    """Retourne les coordonnées et capacités des casernes de Protection Civile de Tunis"""
    return Response(CASERNES_TUNIS)

@api_view(['POST'])
def simuler_accident(request):
    """Génère instantanément un accident réaliste sur Tunis pour tester le WebSocket & Routes API"""
    point = random.choice(POINTS_SIMULATION)
    lat = float(request.data.get('latitude', point["lat"]))
    lng = float(request.data.get('longitude', point["lng"]))
    adresse = request.data.get('adresse', point["adresse"])
    gravite = request.data.get('gravite', point["gravite"])
    description = request.data.get('description', f"Accident de la circulation avec blessés - {adresse}")

    sig = SignalementAccident.objects.create(
        latitude=lat,
        longitude=lng,
        adresse=adresse,
        description=description,
        gravite_estimee=gravite
    )
    alerte = traiter_signalement(sig, valide_par_agent=True)
    notifier_simulateur_accident(alerte)
    return Response({
        "message": "Alerte d'urgence simulée et diffusée en temps réel",
        "alerte_id": alerte.id,
        "statut": alerte.statut,
        "gravite": alerte.gravite,
        "adresse": alerte.adresse,
        "latitude": alerte.latitude,
        "longitude": alerte.longitude,
        "date_confirmation": alerte.date_confirmation.isoformat() if alerte.date_confirmation else None
    })

@api_view(['POST'])
def creer_signalement(request):
    """
    Passerelle d'intégration avec le module Signalements (Étudiant 2) :
    Reçoit les signalements de catégorie ACCIDENT validés ou transmis par l'Espace Citoyen
    pour déclencher le regroupement spatial PostGIS et la diffusion temps réel (< 5s) aux pompiers.
    """
    sig = SignalementAccident.objects.create(
        latitude=float(request.data.get('latitude', 36.8065)),
        longitude=float(request.data.get('longitude', 10.1815)),
        adresse=request.data.get('adresse', 'Avenue Habib Bourguiba, Tunis'),
        description=request.data.get('description', ''),
        gravite_estimee=request.data.get('gravite', 'GRAVE')
    )
    valide_par_agent = bool(request.data.get('valide_par_agent', False))
    alerte = traiter_signalement(sig, valide_par_agent=valide_par_agent)
    notifier_simulateur_accident(alerte)

    return Response({
        "message": "Signalement d'accident transmis et traité par la Protection Civile",
        "alerte_id": alerte.id,
        "statut_alerte": alerte.statut,
        "nb_signalements_concordants": alerte.nb_signalements
    })

@api_view(['POST'])
def changer_statut_intervention(request, alerte_id):
    """
    Workflow strict d'intervention de la Protection Civile :
    'recue' (CONFIRME) -> 'prise_en_charge' -> 'en_cours' (EN_INTERVENTION) -> 'cloturee' (CLOTURE)
    avec création automatique dans JournalAuditIntervention et diffusion WebSocket.
    """
    try:
        alerte = AlerteAccident.objects.get(id=alerte_id)
    except AlerteAccident.DoesNotExist:
        return Response({"error": "Alerte non trouvée"}, status=404)

    statut_brut = str(request.data.get('statut', '')).strip().upper()
    # Normalisation des statuts
    mapping_statuts = {
        'RECUE': 'CONFIRME',
        'CONFIRME': 'CONFIRME',
        'CONFIRMEE': 'CONFIRME',
        'PRISE_EN_CHARGE': 'PRISE_EN_CHARGE',
        'EN_COURS': 'EN_INTERVENTION',
        'EN_INTERVENTION': 'EN_INTERVENTION',
        'CLOTURE': 'CLOTURE',
        'CLOTUREE': 'CLOTURE',
    }
    nouveau_statut = mapping_statuts.get(statut_brut, statut_brut)

    note = request.data.get('note', '')
    matricule = request.data.get('matricule', '')
    intervenant = request.user if request.user.is_authenticated else None

    alerte = enregistrer_changement_statut(
        alerte=alerte,
        nouveau_statut=nouveau_statut,
        intervenant=intervenant,
        matricule=matricule,
        note=note
    )

    if nouveau_statut == 'CLOTURE':
        notifier_simulateur_cloture(alerte.id)

    return Response({
        "alerte_id": alerte.id,
        "nouveau_statut": alerte.statut,
        "date_prise_en_charge": alerte.date_prise_en_charge.isoformat() if alerte.date_prise_en_charge else None,
        "date_en_intervention": alerte.date_en_intervention.isoformat() if alerte.date_en_intervention else None,
        "date_cloture": alerte.date_cloture.isoformat() if alerte.date_cloture else None,
    })

@api_view(['GET'])
def obtenir_audit_intervention(request, alerte_id):
    """Retourne l'historique complet d'audit pour une intervention donnée."""
    try:
        alerte = AlerteAccident.objects.get(id=alerte_id)
    except AlerteAccident.DoesNotExist:
        return Response({"error": "Alerte non trouvée"}, status=404)

    audits = JournalAuditIntervention.objects.filter(alerte=alerte).order_by('-horodatage')
    data = []
    for a in audits:
        data.append({
            "id": a.id,
            "statut_precedent": a.statut_precedent,
            "nouveau_statut": a.nouveau_statut,
            "horodatage": a.horodatage.isoformat(),
            "note_intervention": a.note_intervention,
            "matricule_intervenant": a.matricule_intervenant or (a.intervenant.username if a.intervenant else "Opérateur PC"),
        })
    return Response(data)

@api_view(['POST'])
def calculer_risk_map_zone(request):
    """Endpoint pour obtenir le score de risque d'une zone et ses facteurs explicatifs personnalisés."""
    trafic = float(request.data.get('trafic_index', 2.0))
    travaux = int(request.data.get('presence_travaux', 0))
    pluie = int(request.data.get('meteo_pluie', 0))
    incidents = int(request.data.get('incidents_recents', 1))

    resultat_ml = prediger_risque_zone(trafic, travaux, pluie, incidents)
    return Response({
        "message": "Calcul de la Risk Map effectué avec succès",
        "donnees_zone": resultat_ml
    })

@api_view(['GET'])
def lister_zones_risk_map(request):
    """Retourne la cartographie complète des secteurs du Grand Tunis avec scores et facteurs explicatifs."""
    pluie = int(request.GET.get('meteo_pluie', 0))
    travaux = int(request.GET.get('presence_travaux', 0))
    zones = get_toutes_les_zones_risk_map(meteo_pluie=pluie, presence_travaux=travaux)
    return Response(zones)

@api_view(['POST'])
def assistant_llm_decisionnel(request):
    """
    Endpoint RAG Strict pour l'Assistant IA Décisionnel de la Protection Civile.
    Injecte les données réelles vérifiées et interdit formellement l'hallucination.
    """
    question = request.data.get('question', '').strip()
    if not question:
        return Response({"error": "La question ne peut pas être vide."}, status=400)

    resultat = interroger_assistant_llm(question)
    return Response(resultat)

@api_view(['POST'])
def endpoint_simulation_urgences(request):
    """
    Endpoint de pilotage pour la soutenance (Mode Démo Jury) :
    - mode 'fausse_alerte' : test neutralisation fausse alerte isolée
    - mode 'accident_confirme' : test clustering PostGIS 3 signalements < 5s
    - mode 'risk_map' : génération cartographie Tunis (vert, orange, rouge)
    """
    mode = str(request.data.get('mode', 'accident_confirme')).lower().strip()

    if mode == 'fausse_alerte':
        res = executer_simulation_fausse_alerte()
    elif mode == 'accident_confirme':
        res = executer_simulation_accident_confirme()
    elif mode == 'risk_map':
        res = executer_simulation_risk_map_tunis()
    else:
        return Response({"error": f"Mode inconnu '{mode}'. Choix: fausse_alerte, accident_confirme, risk_map"}, status=400)

    return Response(res)

