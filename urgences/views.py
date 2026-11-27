import random
import threading
import json
import urllib.request
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from config.geo_config import (
    CASERNES_CAP_BON,
    DEFAULT_ADDRESS,
    DEFAULT_COORDS,
    POINTS_SIMULATION_CAP_BON,
    get_public_geo_config,
)
from .models import SignalementAccident, AlerteAccident, Chantier, TronconRoutier, JournalAudit, JournalAuditIntervention
from .services import (
    traiter_signalement,
    diffuser_alerte_temps_reel,
    enregistrer_changement_statut,
)
from .ml_models import (
    prediger_risque_zone,
    get_toutes_les_zones_risk_map,
    SECTEURS_CAP_BON,
)
from .llm_assistant import interroger_assistant_llm
from .simulation import (
    executer_simulation_fausse_alerte,
    executer_simulation_accident_confirme,
    executer_simulation_risk_map_cap_bon,
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

CASERNES_CAP_BON_LIST = CASERNES_CAP_BON
POINTS_SIMULATION = POINTS_SIMULATION_CAP_BON


@api_view(['GET'])
def obtenir_geo_config(request):
    """Retourne la configuration géographique centralisée (Cap Bon / Gouvernorat de Nabeul)."""
    return Response(get_public_geo_config())

@api_view(['GET'])
def lister_alertes(request):
    """Retourne la liste des alertes d'accident récentes (avec cache Redis 30s)"""
    cached = cache.get('alertes_recentes')
    if cached is not None:
        return Response(cached)

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
    cache.set('alertes_recentes', data, timeout=30)
    return Response(data)

@api_view(['GET'])
def lister_casernes(request):
    """Retourne les coordonnées et capacités des casernes de Protection Civile du Cap Bon (cache 5min)"""
    cached = cache.get('casernes_cap_bon')
    if cached is not None:
        return Response(cached)
    cache.set('casernes_cap_bon', CASERNES_CAP_BON_LIST, timeout=300)
    return Response(CASERNES_CAP_BON_LIST)

@api_view(['POST'])
def simuler_accident(request):
    """Génère instantanément un accident réaliste sur le Cap Bon pour tester le WebSocket & Routes API"""
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
    cache.delete('alertes_recentes')
    return Response({
        "message": "Alerte d'urgence simulée et diffusée en temps réel",
        "alerte_id": alerte.id,
        "statut": alerte.statut,
        "gravite": alerte.gravite,
        "adresse": alerte.adresse,
        "zone_nom": alerte.zone_nom,
        "latitude": alerte.latitude,
        "longitude": alerte.longitude,
        "date_confirmation": alerte.date_confirmation.isoformat() if alerte.date_confirmation else None
    })

@api_view(['POST'])
def creer_signalement(request):
    """
    Passerelle d'intégration avec le module Signalements (Étudiant 2) :
    Reçoit les signalements de catégorie ACCIDENT validés ou transmis par l'Espace Citoyen
    pour déclencher le regroupement spatial et la diffusion temps réel (< 5s) aux pompiers.
    """
    sig = SignalementAccident.objects.create(
        latitude=float(request.data.get('latitude', DEFAULT_COORDS['latitude'])),
        longitude=float(request.data.get('longitude', DEFAULT_COORDS['longitude'])),
        adresse=request.data.get('adresse', DEFAULT_ADDRESS),
        description=request.data.get('description', ''),
        gravite_estimee=request.data.get('gravite', 'GRAVE')
    )
    valide_par_agent = bool(request.data.get('valide_par_agent', False))
    alerte = traiter_signalement(sig, valide_par_agent=valide_par_agent)
    notifier_simulateur_accident(alerte)
    cache.delete('alertes_recentes')

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
    cache.delete('alertes_recentes')

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
    """Retourne la cartographie complète des secteurs du Cap Bon avec scores et facteurs explicatifs."""
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
    - mode 'accident_confirme' : test clustering spatial 3 signalements < 5s
    - mode 'risk_map' : génération cartographie Cap Bon (vert, orange, rouge)
    """
    mode = str(request.data.get('mode', 'accident_confirme')).lower().strip()

    if mode == 'fausse_alerte':
        res = executer_simulation_fausse_alerte()
    elif mode == 'accident_confirme':
        res = executer_simulation_accident_confirme()
    elif mode == 'risk_map':
        res = executer_simulation_risk_map_cap_bon()
    else:
        return Response({"error": f"Mode inconnu '{mode}'. Choix: fausse_alerte, accident_confirme, risk_map"}, status=400)

    return Response(res)


def _serialize_chantier(c: Chantier) -> dict:
    return {
        "id": c.id,
        "titre": c.titre,
        "rue_nom": c.rue_nom,
        "street_id": c.street_id,
        "description": c.description,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "priorite": c.priorite,
        "voies_bloquees": c.voies_bloquees,
        "statut": c.statut,
        "date_debut": c.date_debut.isoformat() if hasattr(c.date_debut, "isoformat") else (str(c.date_debut) if c.date_debut else None),
        "date_fin": c.date_fin.isoformat() if hasattr(c.date_fin, "isoformat") else (str(c.date_fin) if c.date_fin else None),
        "declare_par": c.declare_par.username if c.declare_par else None,
        "date_creation": c.date_creation.isoformat() if c.date_creation else None,
    }


@api_view(['GET', 'POST'])
def chantiers_list_create(request):
    """
    GET  /api/chantiers/ : Liste les chantiers déclarés (filtrable par ?statut=EN_COURS, cache Redis 30s).
    POST /api/chantiers/ : Déclare un nouveau chantier (Responsable Municipal).
    """
    if request.method == 'GET':
        statut_filter = request.GET.get('statut')
        if not statut_filter:
            cached = cache.get('chantiers_all')
            if cached is not None:
                return Response(cached)

        qs = Chantier.objects.select_related('declare_par').all()
        if statut_filter:
            qs = qs.filter(statut=statut_filter)
        data = [_serialize_chantier(c) for c in qs]
        if not statut_filter:
            cache.set('chantiers_all', data, timeout=30)
        return Response(data)

    # POST : Création d'un chantier
    titre = str(request.data.get('titre') or '').strip()
    rue_nom = str(request.data.get('rue_nom') or '').strip()
    if not titre or not rue_nom:
        return Response(
            {"detail": "Le titre et le nom de la rue sont obligatoires."},
            status=400,
        )

    try:
        lat = float(request.data.get('latitude', DEFAULT_COORDS['latitude']))
        lng = float(request.data.get('longitude', DEFAULT_COORDS['longitude']))
    except (TypeError, ValueError):
        return Response({"detail": "Coordonnées GPS invalides."}, status=400)

    chantier = Chantier.objects.create(
        titre=titre,
        rue_nom=rue_nom,
        street_id=str(request.data.get('street_id') or '').strip(),
        description=str(request.data.get('description') or '').strip(),
        latitude=lat,
        longitude=lng,
        priorite=str(request.data.get('priorite') or 'MOYENNE').upper(),
        voies_bloquees=max(1, int(request.data.get('voies_bloquees') or 1)),
        statut=str(request.data.get('statut') or 'EN_COURS').upper(),
        date_debut=request.data.get('date_debut') or None,
        date_fin=request.data.get('date_fin') or None,
        declare_par=request.user if request.user.is_authenticated else None,
    )
    cache.delete('chantiers_all')
    _sync_point_geom('urgences_chantier', chantier.id, chantier.latitude, chantier.longitude)
    return Response(_serialize_chantier(chantier), status=201)


@api_view(['PATCH', 'PUT', 'DELETE'])
def chantier_detail(request, chantier_id):
    """
    PATCH/PUT /api/chantiers/<id>/ : Met à jour le statut ou les détails d'un chantier.
    DELETE    /api/chantiers/<id>/ : Supprime un chantier.
    """
    try:
        chantier = Chantier.objects.get(pk=chantier_id)
    except Chantier.DoesNotExist:
        return Response({"detail": "Chantier introuvable."}, status=404)

    if request.method == 'DELETE':
        chantier.delete()
        cache.delete('chantiers_all')
        return Response(status=204)

    for field in ('titre', 'rue_nom', 'street_id', 'description', 'priorite', 'statut'):
        if field in request.data:
            setattr(chantier, field, str(request.data[field]).strip())
    if 'voies_bloquees' in request.data:
        chantier.voies_bloquees = max(1, int(request.data['voies_bloquees']))
    if 'latitude' in request.data:
        chantier.latitude = float(request.data['latitude'])
    if 'longitude' in request.data:
        chantier.longitude = float(request.data['longitude'])
    if 'date_debut' in request.data:
        chantier.date_debut = request.data['date_debut'] or None
    if 'date_fin' in request.data:
        chantier.date_fin = request.data['date_fin'] or None

    chantier.save()
    cache.delete('chantiers_all')
    _sync_point_geom('urgences_chantier', chantier.id, chantier.latitude, chantier.longitude)
    return Response(_serialize_chantier(chantier))


def _sync_point_geom(table_name: str, row_id: int, lat: float, lng: float) -> None:
    """Met à jour la colonne PostGIS `geom` (Point SRID 4326) si PostgreSQL est actif."""
    if connection.vendor != 'postgresql':
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table_name} SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326) WHERE id = %s;",
                [lng, lat, row_id],
            )
    except Exception:
        pass


@api_view(['GET'])
def lister_troncons(request):
    """
    GET /api/troncons/ : Retourne les tronçons routiers (table PostGIS `troncon_routier`)
    avec leurs géométries LineString (GeoJSON + coordonnées) et attributs.
    """
    cached = cache.get('troncons_routiers_all')
    if cached is not None:
        return Response(cached)

    troncons = TronconRoutier.objects.all()
    data = []
    for t in troncons:
        geojson_coords = [[lng, lat] for lat, lng in (t.coordinates or [])]
        data.append({
            "id": t.id,
            "street_id": t.street_id,
            "street_name": t.street_name,
            "zone": t.zone,
            "road_type": t.road_type,
            "base_speed_kmh": t.base_speed_kmh,
            "length_km": t.length_km,
            "proximity_sensitive": t.proximity_sensitive,
            "alternatives": t.alternatives,
            "coordinates": t.coordinates,
            "geometry": {
                "type": "LineString",
                "coordinates": geojson_coords,
            },
        })
    cache.set('troncons_routiers_all', data, timeout=300)
    return Response(data)


@api_view(['GET'])
def troncons_proches(request):
    """
    GET /api/troncons/proches/?lat=36.8475&lng=11.0939&rayon_m=2500
    Utilise l'index spatial GIST + ST_DWithin / ST_Distance de PostGIS sur `troncon_routier.geom`.
    """
    try:
        lat = float(request.GET.get('lat', DEFAULT_COORDS['latitude']))
        lng = float(request.GET.get('lng', DEFAULT_COORDS['longitude']))
        rayon_m = float(request.GET.get('rayon_m', 2500))
    except (TypeError, ValueError):
        return Response({"detail": "Paramètres lat/lng/rayon_m invalides."}, status=400)

    if connection.vendor == 'postgresql':
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT street_id, street_name, zone, road_type, base_speed_kmh, length_km,
                           ROUND(ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)::numeric, 1) AS distance_m
                    FROM troncon_routier
                    WHERE geom IS NOT NULL
                      AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
                    ORDER BY distance_m ASC;
                    """,
                    [lng, lat, lng, lat, rayon_m],
                )
                cols = [col[0] for col in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                for r in rows:
                    r["distance_m"] = float(r["distance_m"])
                return Response({"engine": "PostGIS (GIST + ST_DWithin)", "count": len(rows), "troncons": rows})
        except Exception:
            pass

    # Fallback SQLite
    from .services import distance_metres
    rows = []
    for t in TronconRoutier.objects.all():
        if not t.coordinates:
            continue
        min_d = min(distance_metres(lat, lng, pt[0], pt[1]) for pt in t.coordinates)
        if min_d <= rayon_m:
            rows.append({
                "street_id": t.street_id,
                "street_name": t.street_name,
                "zone": t.zone,
                "road_type": t.road_type,
                "base_speed_kmh": t.base_speed_kmh,
                "length_km": t.length_km,
                "distance_m": round(min_d, 1),
            })
    rows.sort(key=lambda x: x["distance_m"])
    return Response({"engine": "Fallback Python", "count": len(rows), "troncons": rows})


