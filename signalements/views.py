from collections import Counter, defaultdict
from datetime import datetime, time as dt_time, timedelta
import math
from django.contrib.auth import authenticate
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from config.geo_config import DEFAULT_CITY, DEFAULT_COORDS, LOCALITES_CAP_BON_NE, SPATIAL_CONFIG
from urgences.services import distance_metres
from .authentication import generate_jwt_token, get_user_role
from .models import AlerteAnomalie, Signalement, is_responsable_municipal
from .permissions import IsCitoyenOrReadOnly, IsResponsableMunicipal
from .serializers import (
    AlerteAnomalieSerializer,
    ChangerStatutSerializer,
    SignalementResponsableSerializer,
    SignalementSerializer,
    get_client_ip,
)


class SignalementCreationRateThrottle(AnonRateThrottle):
    """
    Rate Limiting anti-spam pour visiteurs anonymes :
    limite les créations anonymes à 5 requêtes par heure par adresse IP.
    """
    scope = 'signalements_create'
    rate = '5/hour'

    def get_cache_key(self, request, view):
        # Les utilisateurs authentifiés utilisent SignalementUserCreationRateThrottle
        if request.user and request.user.is_authenticated:
            return None
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class SignalementUserCreationRateThrottle(UserRateThrottle):
    """
    Quota différencié pour citoyens authentifiés (15 créations/heure par compte utilisateur),
    évitant de pénaliser plusieurs citoyens partageant une même IP (Wi-Fi / NAT).
    Les responsables municipaux sont exemptés.
    """
    scope = 'signalements_create_user'
    rate = '15/hour'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        if is_responsable_municipal(request.user):
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': request.user.pk,
        }


def _trouver_doublon_spatial_temporel(
    categorie: str,
    lat: float,
    lon: float,
    rayon_metres: float = SPATIAL_CONFIG['doublon_rayon_metres'],
    minutes: int = SPATIAL_CONFIG['doublon_fenetre_minutes'],
):
    """
    Détecte si un signalement actif de la même catégorie existe déjà
    dans un rayon de 50 mètres et au cours des 10 dernières minutes.
    """
    fenetre = timezone.now() - timedelta(minutes=minutes)
    delta_lat = (rayon_metres / 111000.0) * 1.5
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    delta_lon = delta_lat / cos_lat
    candidats = (
        Signalement.objects.filter(
            categorie=categorie,
            date_creation__gte=fenetre,
            latitude__gte=lat - delta_lat,
            latitude__lte=lat + delta_lat,
            longitude__gte=lon - delta_lon,
            longitude__lte=lon + delta_lon,
        )
        .exclude(statut=Signalement.Statut.REJETE_SPAM)
        .order_by('-date_creation')
    )
    for cand in candidats:
        if distance_metres(lat, lon, cand.latitude, cand.longitude) <= rayon_metres:
            return cand
    return None


class SignalementViewSet(viewsets.ModelViewSet):
    """
    API ViewSet pour la consultation, le filtrage, la soumission et la supervision
    des signalements citoyens.

    Permissions par rôle :
      - Citoyen / Public : lecture publique (GET) et création (POST) de signalements.
      - Responsable Municipal : modification de statut (PATCH/PUT), suppression (DELETE),
        statistiques avancées (/statistiques/) et supervision globale (/supervision/).

    Filtres disponibles :
      - ?quartier=Nabeul
      - ?statut=EN_ATTENTE
      - ?categorie=NID_DE_POULE
    """
    queryset = Signalement.objects.all().order_by('-date_creation')
    serializer_class = SignalementSerializer
    permission_classes = [IsCitoyenOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    RESPONSABLE_ONLY_ACTIONS = {
        'update',
        'partial_update',
        'destroy',
        'changer_statut',
        'statistiques',
        'dashboard_analytics',
        'supervision',
    }

    def get_permissions(self):
        if self.action in self.RESPONSABLE_ONLY_ACTIONS:
            return [IsResponsableMunicipal()]
        return [IsCitoyenOrReadOnly()]

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return SignalementResponsableSerializer
        if self.action == 'changer_statut':
            return ChangerStatutSerializer
        return SignalementSerializer

    def get_throttles(self):
        # Applique le Rate Limiting différencié (IP anonyme vs utilisateur) sur la création (POST)
        if self.action == 'create':
            return [SignalementCreationRateThrottle(), SignalementUserCreationRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_ip = get_client_ip(request)
        auteur = (
            request.user
            if (request.user and request.user.is_authenticated)
            else None
        )

        validated = serializer.validated_data
        categorie = validated.get('categorie')
        lat = validated.get('latitude')
        lon = validated.get('longitude')

        statut_initial = Signalement.Statut.EN_ATTENTE
        doublon = None
        if categorie and lat is not None and lon is not None:
            doublon = _trouver_doublon_spatial_temporel(categorie, float(lat), float(lon))

        if doublon is not None:
            meme_emetteur = bool(
                (auteur and doublon.auteur_id == auteur.pk)
                or (not auteur and client_ip and doublon.ip_emetteur == client_ip)
            )
            if categorie != Signalement.Categorie.ACCIDENT:
                return Response(
                    {
                        'detail': (
                            "Un signalement similaire a déjà été enregistré à proximité "
                            "(< 50 m) il y a moins de 10 minutes."
                        ),
                        'code': 'DUPLICATE_REPORT',
                        'doublon_id': str(doublon.id),
                        'statut_existant': doublon.statut,
                        'meme_emetteur': meme_emetteur,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            elif meme_emetteur:
                # Répétition d'un même signalement d'accident depuis le même émetteur :
                # marqué comme spam sans déclencher d'alerte Protection Civile redondante.
                statut_initial = Signalement.Statut.REJETE_SPAM

        serializer.save(ip_emetteur=client_ip, auteur=auteur, statut=statut_initial)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        quartier = params.get('quartier')
        statut = params.get('statut')
        categorie = params.get('categorie')
        gravite = params.get('gravite')
        periode = (params.get('periode') or '').lower().strip()
        date_debut = params.get('date_debut')
        date_fin = params.get('date_fin')
        mes_sig = (params.get('mes_signalements') or '').lower()

        if quartier and quartier != 'TOUS':
            queryset = queryset.filter(quartier__icontains=quartier)
        if statut and statut != 'TOUS':
            queryset = queryset.filter(statut=statut)
        elif not is_responsable_municipal(self.request.user):
            queryset = queryset.exclude(statut=Signalement.Statut.REJETE_SPAM)
        if categorie and categorie != 'TOUS':
            queryset = queryset.filter(categorie=categorie)
        if gravite and gravite != 'TOUS':
            queryset = queryset.filter(gravite=gravite)

        # Filtrage par période prédéfinie (24h, 7j, 30j, 90j)
        now = timezone.now()
        periode_map = {
            '24h': timedelta(hours=24),
            '7j': timedelta(days=7),
            '30j': timedelta(days=30),
            '90j': timedelta(days=90),
        }
        if periode in periode_map:
            queryset = queryset.filter(date_creation__gte=now - periode_map[periode])

        # Filtrage par plage de dates explicite
        if date_debut:
            dt_start = parse_datetime(date_debut)
            if dt_start is None:
                d_start = parse_date(date_debut)
                if d_start:
                    dt_start = timezone.make_aware(datetime.combine(d_start, dt_time.min))
            elif timezone.is_naive(dt_start):
                dt_start = timezone.make_aware(dt_start)
            if dt_start:
                queryset = queryset.filter(date_creation__gte=dt_start)

        if date_fin:
            dt_end = parse_datetime(date_fin)
            if dt_end is None:
                d_end = parse_date(date_fin)
                if d_end:
                    dt_end = timezone.make_aware(datetime.combine(d_end, dt_time.max))
            elif timezone.is_naive(dt_end):
                dt_end = timezone.make_aware(dt_end)
            if dt_end:
                queryset = queryset.filter(date_creation__lte=dt_end)

        if mes_sig in ('1', 'true', 'yes') and self.request.user and self.request.user.is_authenticated:
            queryset = queryset.filter(auteur=self.request.user)

        return queryset

    @action(
        detail=True,
        methods=['patch', 'post'],
        url_path='changer-statut',
        permission_classes=[IsResponsableMunicipal],
    )
    def changer_statut(self, request, pk=None):
        """
        Action réservée au Responsable Municipal pour faire évoluer le statut
        d'un signalement (EN_ATTENTE -> CONFIRME / EN_COURS / RESOLU / REJETE_SPAM).
        """
        signalement = self.get_object()
        serializer = ChangerStatutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        signalement.statut = serializer.validated_data['statut']
        signalement.save(update_fields=['statut', 'date_mise_a_jour'])
        return Response(
            SignalementResponsableSerializer(
                signalement,
                context={'request': request, 'view': self}
            ).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=['get'],
        url_path='statistiques',
        permission_classes=[IsResponsableMunicipal],
    )
    def statistiques(self, request):
        """
        Statistiques avancées, agrégations spatiales (PostGIS / fallback grille SQLite),
        points de heatmap pondérés, série temporelle et indicateurs INPDP réservés
        au Responsable Municipal. Supporte tous les filtres (quartier, période, gravité, statut, catégorie).
        """
        qs = self.filter_queryset(self.get_queryset())
        rows = list(
            qs.values(
                'categorie',
                'gravite',
                'statut',
                'quartier',
                'latitude',
                'longitude',
                'visages_plaques_floutes',
                'nb_zones_floutees',
                'date_creation',
            )
        )

        total = len(rows)
        par_statut: dict = Counter()
        par_categorie: dict = Counter()
        par_gravite: dict = Counter()
        par_quartier_counter: dict = Counter()
        photos_floutees = 0
        total_zones_floutees = 0

        # Poids de gravité pour la Heatmap et le calcul de densité
        grav_weights = {
            Signalement.Gravite.CRITIQUE: 1.0,
            Signalement.Gravite.ELEVEE: 0.8,
            Signalement.Gravite.MOYENNE: 0.55,
            Signalement.Gravite.FAIBLE: 0.3,
        }

        heatmap_points = []
        grid_cells = defaultdict(lambda: {
            'lats': [],
            'lngs': [],
            'quartiers': Counter(),
            'categories': Counter(),
            'nb_signalements': 0,
            'nb_actifs': 0,
            'nb_critiques_eleves': 0,
            'score_densite': 0.0,
        })
        daily_buckets = defaultdict(lambda: {
            'total': 0,
            'en_attente': 0,
            'en_cours': 0,
            'resolus': 0,
        })

        voirie_active = 0
        grid_step_deg = float(SPATIAL_CONFIG['grid_step_deg'])
        max_hotspots = int(SPATIAL_CONFIG['max_hotspots_zones'])
        for r in rows:
            st = r['statut']
            cat = r['categorie']
            grav = r['gravite']
            qtr = r['quartier'] or DEFAULT_CITY

            par_statut[st] += 1
            par_categorie[cat] += 1
            par_gravite[grav] += 1
            par_quartier_counter[qtr] += 1

            if r['visages_plaques_floutes']:
                photos_floutees += 1
            total_zones_floutees += int(r['nb_zones_floutees'] or 0)

            est_actif = st not in (Signalement.Statut.RESOLU, Signalement.Statut.REJETE_SPAM)
            if est_actif and cat in (Signalement.Categorie.NID_DE_POULE, Signalement.Categorie.SIGNALISATION):
                voirie_active += 1

            # Pondération Heatmap
            base_w = grav_weights.get(grav, 0.5)
            if st == Signalement.Statut.RESOLU:
                w = round(base_w * 0.25, 3)
            elif st == Signalement.Statut.REJETE_SPAM:
                w = 0.05
            else:
                w = base_w

            lat = float(r['latitude'])
            lng = float(r['longitude'])
            if st != Signalement.Statut.REJETE_SPAM:
                heatmap_points.append([round(lat, 6), round(lng, 6), w])

                # Agrégation spatiale par grille régionale configurable
                cell_key = (round(lat / grid_step_deg) * grid_step_deg, round(lng / grid_step_deg) * grid_step_deg)
                cell = grid_cells[cell_key]
                cell['lats'].append(lat)
                cell['lngs'].append(lng)
                cell['quartiers'][qtr] += 1
                cell['categories'][cat] += 1
                cell['nb_signalements'] += 1
                if est_actif:
                    cell['nb_actifs'] += 1
                if grav in (Signalement.Gravite.CRITIQUE, Signalement.Gravite.ELEVEE):
                    cell['nb_critiques_eleves'] += 1
                cell['score_densite'] += w

            # Série temporelle journalière
            dt_val = r['date_creation']
            if dt_val:
                day_str = timezone.localtime(dt_val).date().isoformat() if timezone.is_aware(dt_val) else dt_val.date().isoformat()
                b = daily_buckets[day_str]
                b['total'] += 1
                if st == Signalement.Statut.EN_ATTENTE:
                    b['en_attente'] += 1
                elif st in (Signalement.Statut.CONFIRME, Signalement.Statut.EN_COURS):
                    b['en_cours'] += 1
                elif st == Signalement.Statut.RESOLU:
                    b['resolus'] += 1

        par_quartier = [
            {'quartier': q, 'total': c}
            for q, c in sorted(par_quartier_counter.items(), key=lambda kv: kv[1], reverse=True)
        ]

        resolus = par_statut.get(Signalement.Statut.RESOLU, 0)
        taux_resolution = round((resolus / total) * 100, 2) if total > 0 else 0.0

        en_cours_count = par_statut.get(Signalement.Statut.EN_COURS, 0)
        confirmes_count = par_statut.get(Signalement.Statut.CONFIRME, 0)
        chantiers_actifs = en_cours_count + confirmes_count
        incidents_en_attente = par_statut.get(Signalement.Statut.EN_ATTENTE, 0)

        # Zones à forte densité (PostGIS ST_SnapToGrid si PostgreSQL/PostGIS sans filtre actif, sinon grille optimisée)
        has_active_filters = any(
            request.query_params.get(k) not in (None, '', 'TOUS')
            for k in ('quartier', 'statut', 'categorie', 'gravite', 'periode', 'date_debut', 'date_fin', 'mes_signalements')
        )
        zones_haute_densite = []
        used_postgis = False
        if not has_active_filters and connection.vendor == 'postgresql' and 'gis' in connection.settings_dict.get('ENGINE', ''):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            ROUND(AVG(latitude)::numeric, 6) AS lat_c,
                            ROUND(AVG(longitude)::numeric, 6) AS lng_c,
                            MAX(quartier) AS zone,
                            COUNT(*) AS nb_sig
                        FROM signalements_signalement
                        WHERE statut != 'REJETE_SPAM'
                        GROUP BY ST_SnapToGrid(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), %s)
                        ORDER BY nb_sig DESC
                        LIMIT %s
                        """,
                        [grid_step_deg, max_hotspots],
                    )
                    for lat_c, lng_c, zone_lbl, nb_sig in cursor.fetchall():
                        zones_haute_densite.append({
                            'zone': zone_lbl,
                            'latitude': float(lat_c),
                            'longitude': float(lng_c),
                            'nb_signalements': int(nb_sig),
                            'nb_actifs': int(nb_sig),
                            'nb_critiques_eleves': 0,
                            'score_densite': float(nb_sig),
                            'categorie_dominante': 'MIXTE',
                        })
                    used_postgis = True
            except Exception:
                used_postgis = False

        if not used_postgis:
            for cell in grid_cells.values():
                n = cell['nb_signalements']
                zones_haute_densite.append({
                    'zone': cell['quartiers'].most_common(1)[0][0],
                    'latitude': round(sum(cell['lats']) / n, 6),
                    'longitude': round(sum(cell['lngs']) / n, 6),
                    'nb_signalements': n,
                    'nb_actifs': cell['nb_actifs'],
                    'nb_critiques_eleves': cell['nb_critiques_eleves'],
                    'score_densite': round(cell['score_densite'], 2),
                    'categorie_dominante': cell['categories'].most_common(1)[0][0],
                })
            zones_haute_densite.sort(key=lambda z: (z['score_densite'], z['nb_signalements']), reverse=True)
            zones_haute_densite = zones_haute_densite[:max_hotspots]

        # Série temporelle ordonnée (jusqu'aux 14 derniers jours actifs ou fenêtre continue de 7j si vide)
        if daily_buckets:
            evolution_temporelle = [
                {'date': d, **daily_buckets[d]}
                for d in sorted(daily_buckets.keys())[-14:]
            ]
        else:
            today = timezone.localdate()
            evolution_temporelle = [
                {
                    'date': (today - timedelta(days=i)).isoformat(),
                    'total': 0,
                    'en_attente': 0,
                    'en_cours': 0,
                    'resolus': 0,
                }
                for i in range(6, -1, -1)
            ]

        anomalies_actives_count = AlerteAnomalie.objects.filter(
            statut=AlerteAnomalie.Statut.ACTIVE
        ).count()

        return Response(
            {
                'total_signalements': total,
                'par_statut': dict(par_statut),
                'par_categorie': dict(par_categorie),
                'par_gravite': dict(par_gravite),
                'par_quartier': par_quartier,
                'conformite_inpdp': {
                    'photos_floutees': photos_floutees,
                    'total_zones_floutees': total_zones_floutees,
                },
                'taux_resolution_pourcent': taux_resolution,
                'chantiers_actifs': chantiers_actifs,
                'incidents_en_attente': incidents_en_attente,
                'details_chantiers': {
                    'en_cours': en_cours_count,
                    'confirmes': confirmes_count,
                    'voirie_active': voirie_active,
                },
                'zones_haute_densite': zones_haute_densite,
                'heatmap_points': heatmap_points,
                'evolution_temporelle': evolution_temporelle,
                'anomalies_actives_count': anomalies_actives_count,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=['get'],
        url_path='dashboard-analytics',
        permission_classes=[IsResponsableMunicipal],
    )
    def dashboard_analytics(self, request):
        """Alias vers /statistiques/ exposant les KPIs, séries temporelles et points Heatmap."""
        return self.statistiques(request)

    @action(
        detail=False,
        methods=['get'],
        url_path='supervision',
        permission_classes=[IsResponsableMunicipal],
    )
    def supervision(self, request):
        """
        Rapport global de supervision municipale incluant les données sensibles
        (IP émettrice, auteur, détection spam) réservé au Responsable Municipal.
        """
        queryset = self.filter_queryset(self.get_queryset())
        serializer = SignalementResponsableSerializer(
            queryset,
            many=True,
            context={'request': request, 'view': self},
        )
        return Response(
            {
                'total': queryset.count(),
                'signalements': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class LoginSignalementView(APIView):
    """
    Endpoint d'authentification délivrant un jeton Bearer JWT signé HS256
    ainsi que le rôle de l'utilisateur (CITOYEN ou RESPONSABLE_MUNICIPAL).
    Accepte nom d'utilisateur ou adresse email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        raw_ident = (
            request.data.get('username')
            or request.data.get('email')
            or ''
        ).strip()
        password = request.data.get('password') or ''

        if not raw_ident or not password:
            return Response(
                {'detail': "Veuillez renseigner l'identifiant / email et le mot de passe."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = raw_ident
        if '@' in raw_ident:
            from django.contrib.auth.models import User
            matched_user = User.objects.filter(email__iexact=raw_ident).first()
            if matched_user:
                username = matched_user.username

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {'detail': 'Identifiants invalides.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {'detail': 'Ce compte est désactivé.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = generate_jwt_token(user)
        return Response(
            {
                'access': token,
                'token_type': 'Bearer',
                'user': {
                    'id': user.pk,
                    'username': user.username,
                    'email': user.email,
                    'role': get_user_role(user),
                    'est_responsable_municipal': is_responsable_municipal(user),
                },
            },
            status=status.HTTP_200_OK,
        )


class RegisterSignalementView(APIView):
    """
    Endpoint d'inscription pour créer un compte (Citoyen ou Responsable Municipal).
    Délivre immédiatement un jeton JWT et initialise le ProfilUtilisateur avec le bon rôle.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth.models import User
        from .models import ProfilUtilisateur, UserRole

        email = (request.data.get('email') or '').strip()
        password = request.data.get('password') or ''
        role = request.data.get('role') or UserRole.CITOYEN
        username = (
            request.data.get('username')
            or (email.split('@')[0] if email else '')
            or ''
        ).strip()

        if not email or not password:
            return Response(
                {'detail': "L'adresse email et le mot de passe sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email__iexact=email).exists() or (
            '@' not in email and User.objects.filter(username__iexact=email).exists()
        ):
            return Response(
                {'detail': 'Un compte avec cet identifiant ou adresse email existe déjà.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Génération d'un nom d'utilisateur unique
        base_username = username if username else 'citoyen'
        final_username = base_username
        suffix = 1
        while User.objects.filter(username__iexact=final_username).exists():
            final_username = f"{base_username}_{suffix}"
            suffix += 1

        user = User.objects.create_user(
            username=final_username,
            email=email,
            password=password,
        )

        if role == UserRole.RESPONSABLE_MUNICIPAL:
            target_role = UserRole.RESPONSABLE_MUNICIPAL
        elif role == UserRole.PROTECTION_CIVILE:
            target_role = UserRole.PROTECTION_CIVILE
        else:
            target_role = UserRole.CITOYEN
        profil, _ = ProfilUtilisateur.objects.get_or_create(user=user)
        profil.role = target_role
        profil.save()
        user.refresh_from_db()

        token = generate_jwt_token(user)
        return Response(
            {
                'access': token,
                'token_type': 'Bearer',
                'user': {
                    'id': user.pk,
                    'username': user.username,
                    'email': user.email,
                    'role': get_user_role(user),
                    'est_responsable_municipal': is_responsable_municipal(user),
                },
                'message': 'Compte créé avec succès.',
            },
            status=status.HTTP_201_CREATED,
        )


class CurrentUserProfileView(APIView):
    """Retourne les informations et le rôle de l'utilisateur authentifié."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                'id': user.pk,
                'username': user.username,
                'email': user.email,
                'role': get_user_role(user),
                'est_responsable_municipal': is_responsable_municipal(user),
            },
            status=status.HTTP_200_OK,
        )


class AnomalieListView(APIView):
    """
    Liste les alertes d'anomalies détectées par Isolation Forest pour le Responsable Municipal.
    """
    permission_classes = [IsResponsableMunicipal]

    def get(self, request):
        statut_filter = request.query_params.get('statut')
        qs = AlerteAnomalie.objects.select_related('acquittee_par').all()
        if statut_filter in (AlerteAnomalie.Statut.ACTIVE, AlerteAnomalie.Statut.ACQUITTEE):
            qs = qs.filter(statut=statut_filter)

        # Place les anomalies actives en tête puis trie par date décroissante
        qs = qs.order_by('statut', '-date_detection')[:50]
        serializer = AlerteAnomalieSerializer(qs, many=True)
        total_actives = AlerteAnomalie.objects.filter(statut=AlerteAnomalie.Statut.ACTIVE).count()
        return Response(
            {
                'modele': 'IsolationForest (Non supervisé)',
                'total_actives': total_actives,
                'anomalies': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class AnomalieAnalyseView(APIView):
    """
    Déclenche un scan manuel complet Isolation Forest sur toutes les zones actives.
    """
    permission_classes = [IsResponsableMunicipal]

    def post(self, request):
        from .anomaly_detector import scanner_toutes_anomalies
        fenetre = int(request.data.get('fenetre_heures', 6))
        detectees = scanner_toutes_anomalies(fenetre_heures=max(1, min(72, fenetre)))
        qs = AlerteAnomalie.objects.select_related('acquittee_par').all().order_by('statut', '-date_detection')[:50]
        return Response(
            {
                'message': f"Analyse Isolation Forest terminée : {len(detectees)} anomalie(s) active(s) détectée(s).",
                'nb_detectees': len(detectees),
                'anomalies': AlerteAnomalieSerializer(qs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class AnomalieSimulerView(APIView):
    """
    Endpoint de démonstration réservé au Responsable Municipal :
    Génère 3 signalements concordants et réalistes espacés d'environ 80 m
    dans une même zone/catégorie puis exécute detect_anomalies_6h() (IsolationForest).
    """
    permission_classes = [IsResponsableMunicipal]

    def post(self, request):
        from .anomaly_detector import detect_anomalies_6h

        req_quartier = (request.data.get('quartier') or '').strip() if isinstance(request.data, dict) else ''
        req_categorie = (request.data.get('categorie') or '').strip() if isinstance(request.data, dict) else ''

        localite_match = next(
            (loc for loc in LOCALITES_CAP_BON_NE if loc['nom'].lower() == req_quartier.lower()),
            None,
        )
        quartier = localite_match['nom'] if localite_match else (req_quartier or DEFAULT_CITY)
        lat_base = float(localite_match['lat']) if localite_match else float(DEFAULT_COORDS['latitude'])
        lng_base = float(localite_match['lng']) if localite_match else float(DEFAULT_COORDS['longitude'])

        valid_categories = {c[0] for c in Signalement.Categorie.choices}
        categorie = req_categorie if req_categorie in valid_categories else Signalement.Categorie.ECLAIRAGE

        # 3 signalements réalistes espacés d'environ 80 m (> 50 m anti-doublon)
        specs = [
            {
                'dlat': 0.0,
                'dlng': 0.0,
                'gravite': Signalement.Gravite.CRITIQUE,
                'adresse': f"Avenue des Martyrs, {quartier}",
                'description': (
                    "Panne complète de l'éclairage public sur le tronçon central — "
                    "visibilité nulle signalée par les riverains."
                ),
            },
            {
                'dlat': 0.00072,  # ~80 m au nord
                'dlng': 0.00010,
                'gravite': Signalement.Gravite.CRITIQUE,
                'adresse': f"Carrefour Centre Commercial, {quartier}",
                'description': (
                    "Plusieurs candélabres hors service au niveau du carrefour — "
                    "risque élevé pour la circulation nocturne."
                ),
            },
            {
                'dlat': -0.00010,
                'dlng': 0.00090,  # ~80 m à l'est
                'gravite': Signalement.Gravite.ELEVEE,
                'adresse': f"Rue Principale / Secteur Urbain, {quartier}",
                'description': (
                    "Coupure d'éclairage persistante sur l'axe secondaire reliant les habitations."
                ),
            },
        ]

        client_ip = get_client_ip(request)
        generes = []
        for spec in specs:
            sig = Signalement.objects.create(
                auteur=request.user,
                categorie=categorie,
                gravite=spec['gravite'],
                statut=Signalement.Statut.EN_ATTENTE,
                description=spec['description'],
                latitude=round(lat_base + spec['dlat'], 6),
                longitude=round(lng_base + spec['dlng'], 6),
                adresse_texte=spec['adresse'],
                quartier=quartier,
                ip_emetteur=client_ip,
            )
            generes.append({
                'id': str(sig.id),
                'quartier': sig.quartier,
                'categorie': sig.categorie,
                'gravite': sig.gravite,
                'latitude': sig.latitude,
                'longitude': sig.longitude,
                'adresse_texte': sig.adresse_texte,
            })

        detectees = detect_anomalies_6h()
        alerte_obj = (
            AlerteAnomalie.objects.select_related('acquittee_par')
            .filter(
                quartier=quartier,
                categorie=categorie,
                statut=AlerteAnomalie.Statut.ACTIVE,
            )
            .order_by('-date_detection')
            .first()
        )
        qs_anomalies = (
            AlerteAnomalie.objects.select_related('acquittee_par')
            .all()
            .order_by('statut', '-date_detection')[:50]
        )

        return Response(
            {
                'message': (
                    f"Simulation exécutée : 3 signalements concordants générés à {quartier} "
                    f"et analysés par IsolationForest ({len(detectees)} anomalie(s) active(s))."
                ),
                'modele': 'IsolationForest (Non supervisé)',
                'quartier': quartier,
                'categorie': categorie,
                'signalements_generes': generes,
                'nb_detectees': len(detectees),
                'alerte': AlerteAnomalieSerializer(alerte_obj).data if alerte_obj else None,
                'anomalies': AlerteAnomalieSerializer(qs_anomalies, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AnomalieAcquitterView(APIView):
    """
    Permet au Responsable Municipal d'acquitter une alerte d'anomalie IA traitée.
    """
    permission_classes = [IsResponsableMunicipal]

    def post(self, request, pk):
        try:
            anomalie = AlerteAnomalie.objects.get(pk=pk)
        except AlerteAnomalie.DoesNotExist:
            return Response({'detail': 'Alerte anomalie introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        if anomalie.statut != AlerteAnomalie.Statut.ACQUITTEE:
            anomalie.statut = AlerteAnomalie.Statut.ACQUITTEE
            anomalie.date_acquittement = timezone.now()
            anomalie.acquittee_par = request.user
            anomalie.save(update_fields=['statut', 'date_acquittement', 'acquittee_par', 'date_mise_a_jour'])

        return Response(AlerteAnomalieSerializer(anomalie).data, status=status.HTTP_200_OK)

