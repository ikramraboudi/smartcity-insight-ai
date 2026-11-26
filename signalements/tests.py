import os
import io
import shutil
import tempfile
from datetime import timedelta
from PIL import Image, ImageDraw
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .anomaly_detector import evaluer_anomalie_zone, scanner_toutes_anomalies
from .models import (
    AlerteAnomalie,
    ProfilUtilisateur,
    Signalement,
    UserRole,
    is_responsable_municipal,
)
from .privacy_blur import anonymize_image

# Création d'un dossier temporaire pour isoler les fichiers médias générés par les tests
TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def _create_synthetic_plate_image() -> bytes:
    """Génère une image simulant une plaque d'immatriculation bien contrastée avec métadonnées EXIF."""
    img = Image.new('RGB', (400, 300), color=(120, 120, 120))
    draw = ImageDraw.Draw(img)
    # Rectangle de format plaque d'immatriculation (ratio ~ 3.5)
    draw.rectangle([100, 120, 240, 160], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    draw.text((120, 132), "123 TUN 456", fill=(0, 0, 0))

    buffer = io.BytesIO()
    exif = img.getexif()
    exif[0x010F] = "Samsung Citizen"
    exif[0x0110] = "Galaxy S22"
    img.save(buffer, format='JPEG', exif=exif)
    buffer.seek(0)
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PrivacyBlurServiceTest(TestCase):
    """
    Tests unitaires du service de vision par ordinateur (anonymisation & floutage INPDP).
    """

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_anonymize_image_detects_and_blurs(self):
        """Vérifie que la fonction anonymize_image s'exécute, détecte la plaque et purge les EXIF."""
        raw_bytes = _create_synthetic_plate_image()
        upload_file = SimpleUploadedFile("incident_plaque.jpg", raw_bytes, content_type="image/jpeg")

        processed_file, zones_detected, success = anonymize_image(upload_file)

        self.assertTrue(success, "Le service d'anonymisation doit retourner un succès.")
        self.assertGreaterEqual(zones_detected, 1, "La plaque d'immatriculation doit être détectée.")
        self.assertIsNotNone(processed_file, "Un fichier processed ContentFile doit être renvoyé.")

        # Vérification de la suppression intégrale des métadonnées EXIF (Conformité INPDP)
        out_img = Image.open(processed_file)
        out_exif = out_img.getexif()
        self.assertEqual(len(out_exif.keys()), 0, "Toutes les métadonnées EXIF doivent être supprimées.")

    def test_signalement_auto_blur_on_save(self):
        """
        Vérifie l'intégration Django : à la création d'un signalement avec photo,
        le floutage s'exécute automatiquement, les drapeaux passent à True et
        le fichier anonymisé est enregistré sur le disque.
        """
        raw_bytes = _create_synthetic_plate_image()
        uploaded = SimpleUploadedFile("citoyen_nid_de_poule.jpg", raw_bytes, content_type="image/jpeg")

        signalement = Signalement.objects.create(
            categorie=Signalement.Categorie.NID_DE_POULE,
            gravite=Signalement.Gravite.MOYENNE,
            description="Nid-de-poule dangereux avenue des Martyrs, Kélibia",
            latitude=36.8475,
            longitude=11.0939,
            adresse_texte="Avenue des Martyrs, Kélibia",
            quartier="Kélibia",
            photo_floutee=uploaded,
        )

        # 1. Vérification des indicateurs d'anonymisation dans le modèle
        self.assertTrue(signalement.visages_plaques_floutes, "Le drapeau visages_plaques_floutes doit passer à True.")
        self.assertGreaterEqual(signalement.nb_zones_floutees, 1, "Le nombre de zones floutées doit être supérieur ou égal à 1.")

        # 2. Vérification de la présence physique de l'image sur le disque (MEDIA_ROOT)
        self.assertTrue(bool(signalement.photo_floutee), "Le champ photo_floutee doit contenir un fichier.")
        self.assertTrue(os.path.exists(signalement.photo_floutee.path), "Le fichier anonymisé doit exister sur le disque.")
        self.assertGreater(os.path.getsize(signalement.photo_floutee.path), 0, "Le fichier ne doit pas être vide.")

        # 3. Vérification de la purge EXIF sur le fichier stocké sur le disque
        saved_img = Image.open(signalement.photo_floutee.path)
        self.assertEqual(len(saved_img.getexif().keys()), 0, "L'image stockée ne doit contenir aucune donnée EXIF.")

    def test_signalement_without_photo(self):
        """Vérifie qu'un signalement sans photo se sauvegarde sans erreur ni déclenchement inutile."""
        signalement = Signalement.objects.create(
            categorie=Signalement.Categorie.ECLAIRAGE,
            gravite=Signalement.Gravite.FAIBLE,
            description="Lampadaire éteint",
            latitude=36.8906,
            longitude=11.1197,
            adresse_texte="Route Côtière C27, Hammam El Ghezaz",
        )
        self.assertFalse(signalement.visages_plaques_floutes)
        self.assertEqual(signalement.nb_zones_floutees, 0)
        self.assertFalse(bool(signalement.photo_floutee))


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class SignalementAPITest(TestCase):
    """
    Tests d'intégration de l'API REST DRF (/api/signalements/) et du Rate Limiting anti-spam.
    """

    def setUp(self):
        self.client = APIClient()
        cache.clear()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_create_signalement_api_with_photo(self):
        """Vérifie la création d'un signalement via POST API avec téléversement d'image et anonymisation."""
        raw_bytes = _create_synthetic_plate_image()
        photo = SimpleUploadedFile("api_plaque.jpg", raw_bytes, content_type="image/jpeg")

        payload = {
            'categorie': 'NID_DE_POULE',
            'gravite': 'MOYENNE',
            'description': 'Nid-de-poule signalé via application mobile citoyenne',
            'latitude': 36.8475,
            'longitude': 11.0939,
            'adresse_texte': 'Avenue des Martyrs, Kélibia',
            'quartier': 'Kélibia',
            'photo_floutee': photo,
        }

        response = self.client.post('/api/signalements/', payload, format='multipart', REMOTE_ADDR='196.203.45.10')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('id', data)
        self.assertEqual(data['categorie'], 'NID_DE_POULE')
        self.assertEqual(data['quartier'], 'Kélibia')
        self.assertEqual(data['statut'], 'EN_ATTENTE')
        self.assertTrue(data['visages_plaques_floutes'])
        self.assertGreaterEqual(data['nb_zones_floutees'], 1)
        self.assertEqual(data['ip_emetteur'], '196.203.45.10')
        self.assertIsNotNone(data['photo_floutee'])

    def test_rate_limiting_anti_spam(self):
        """
        Vérifie le Rate Limiting (5 créations max par heure par IP).
        Le 6ème signalement émis en moins d'1h depuis la même IP doit retourner 429 Too Many Requests.
        """
        cache.clear()
        client_ip = '197.100.50.25'

        payload = {
            'categorie': 'ACCIDENT',
            'gravite': 'ELEVEE',
            'description': 'Accident léger sur la voie publique',
            'latitude': 36.9350,
            'longitude': 11.1050,
            'adresse_texte': 'Traverse C27, Dar Allouche',
            'quartier': 'Dar Allouche',
        }

        # Les 5 premiers signalements doivent être acceptés (201 Created)
        for i in range(5):
            res = self.client.post('/api/signalements/', payload, format='json', REMOTE_ADDR=client_ip)
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, f"Requête {i+1} doit réussir.")

        # Le 6ème signalement doit être bloqué par le Throttle (429 Too Many Requests)
        blocked_res = self.client.post('/api/signalements/', payload, format='json', REMOTE_ADDR=client_ip)
        self.assertEqual(
            blocked_res.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Le 6ème signalement doit être rejeté avec le code HTTP 429."
        )

        # Une adresse IP différente doit toujours pouvoir poster sans être bloquée
        other_ip_res = self.client.post('/api/signalements/', payload, format='json', REMOTE_ADDR='197.200.10.99')
        self.assertEqual(other_ip_res.status_code, status.HTTP_201_CREATED)

    def test_filter_signalements_by_quartier_and_statut(self):
        """Vérifie le filtrage de l'API par quartier, statut et catégorie."""
        Signalement.objects.create(
            categorie=Signalement.Categorie.DECHETS,
            latitude=36.8906,
            longitude=11.1197,
            quartier="Hammam El Ghezaz",
            statut=Signalement.Statut.EN_ATTENTE,
        )
        Signalement.objects.create(
            categorie=Signalement.Categorie.ECLAIRAGE,
            latitude=36.8475,
            longitude=11.0939,
            quartier="Kélibia",
            statut=Signalement.Statut.RESOLU,
        )

        # Filtre par localité
        res_quartier = self.client.get('/api/signalements/?quartier=Hammam%20El%20Ghezaz')
        self.assertEqual(res_quartier.status_code, status.HTTP_200_OK)
        items = res_quartier.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['quartier'], 'Hammam El Ghezaz')

        # Filtre par statut
        res_statut = self.client.get('/api/signalements/?statut=RESOLU')
        self.assertEqual(res_statut.status_code, status.HTTP_200_OK)
        items_statut = res_statut.json()
        self.assertEqual(len(items_statut), 1)
        self.assertEqual(items_statut[0]['statut'], 'RESOLU')


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class SignalementSecurityPermissionsTest(TestCase):
    """
    Tests unitaires de sécurité et contrôle d'accès par rôles (RBAC) :
      - Citoyen / Utilisateur non authentifié : création autorisée, actions de supervision/statut bloquées (403).
      - Responsable Municipal : accès complet de supervision, statistiques et gestion des statuts.
    """

    def setUp(self):
        self.client = APIClient()
        cache.clear()

        # 1. Création d'un utilisateur Citoyen (profil CITOYEN créé automatiquement par signal)
        self.citoyen = User.objects.create_user(
            username='citoyen_capbon',
            password='CitoyenPassword123!'
        )

        # 2. Création d'un Responsable Municipal
        self.responsable = User.objects.create_user(
            username='responsable_mairie',
            password='MairiePassword123!'
        )
        self.responsable.profil.role = UserRole.RESPONSABLE_MUNICIPAL
        self.responsable.profil.save()

        # 3. Signalement de test
        self.signalement = Signalement.objects.create(
            categorie=Signalement.Categorie.NID_DE_POULE,
            gravite=Signalement.Gravite.ELEVEE,
            description="Affaissement chaussée avenue des Martyrs",
            latitude=36.8475,
            longitude=11.0939,
            adresse_texte="Avenue des Martyrs, Kélibia",
            quartier="Kélibia",
            ip_emetteur="196.200.10.50",
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_profil_roles_attribution(self):
        """Vérifie l'attribution automatique des rôles et la reconnaissance via groupe Django."""
        self.assertEqual(self.citoyen.profil.role, UserRole.CITOYEN)
        self.assertFalse(is_responsable_municipal(self.citoyen))

        self.assertEqual(self.responsable.profil.role, UserRole.RESPONSABLE_MUNICIPAL)
        self.assertTrue(is_responsable_municipal(self.responsable))

        # Vérifie aussi la reconnaissance via les groupes natifs Django
        citoyen_groupe = User.objects.create_user(username='agent_groupe', password='Pwd123!')
        self.assertFalse(is_responsable_municipal(citoyen_groupe))
        groupe_resp, _ = Group.objects.get_or_create(name=UserRole.RESPONSABLE_MUNICIPAL)
        citoyen_groupe.groups.add(groupe_resp)
        self.assertTrue(is_responsable_municipal(citoyen_groupe))

    def test_unauthenticated_blocked_on_responsable_actions(self):
        """Un utilisateur non authentifié reçoit HTTP 403 sur toutes les actions du Responsable Municipal."""
        url_detail = f'/api/signalements/{self.signalement.id}/'

        res_patch = self.client.patch(url_detail, {'statut': 'RESOLU'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        res_put = self.client.put(url_detail, {'statut': 'RESOLU'}, format='json')
        self.assertEqual(res_put.status_code, status.HTTP_403_FORBIDDEN)

        res_delete = self.client.delete(url_detail)
        self.assertEqual(res_delete.status_code, status.HTTP_403_FORBIDDEN)

        res_changer = self.client.patch(f'{url_detail}changer-statut/', {'statut': 'RESOLU'}, format='json')
        self.assertEqual(res_changer.status_code, status.HTTP_403_FORBIDDEN)

        res_stats = self.client.get('/api/signalements/statistiques/')
        self.assertEqual(res_stats.status_code, status.HTTP_403_FORBIDDEN)

        res_supervision = self.client.get('/api/signalements/supervision/')
        self.assertEqual(res_supervision.status_code, status.HTTP_403_FORBIDDEN)

        self.signalement.refresh_from_db()
        self.assertEqual(self.signalement.statut, Signalement.Statut.EN_ATTENTE)

    def test_citoyen_can_create_but_blocked_on_responsable_actions(self):
        """
        Un citoyen authentifié peut déposer un signalement (sans pouvoir forcer son statut),
        ne voit pas les IP d'autres citoyens, et reçoit HTTP 403 sur les actions municipales.
        """
        self.client.force_authenticate(user=self.citoyen)

        # 1. Le citoyen peut créer un signalement (POST) mais pas forcer statut=RESOLU
        payload = {
            'categorie': 'DECHETS',
            'gravite': 'MOYENNE',
            'description': 'Dépôt de déchets sur le trottoir',
            'latitude': 37.0500,
            'longitude': 11.0144,
            'quartier': 'El Haouaria',
            'statut': 'RESOLU',  # Tentative d'élévation de privilège à ignorer
        }
        res_create = self.client.post('/api/signalements/', payload, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        created_data = res_create.json()
        self.assertEqual(created_data['statut'], Signalement.Statut.EN_ATTENTE)
        self.assertEqual(created_data['auteur'], self.citoyen.id)

        # 2. En lecture publique, l'IP émetteur est masquée au citoyen (INPDP)
        res_list = self.client.get('/api/signalements/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        for item in res_list.json():
            self.assertNotIn('ip_emetteur', item)

        # 3. Le citoyen est bloqué (403) s'il tente de modifier le statut ou d'accéder aux stats/supervision
        url_detail = f'/api/signalements/{self.signalement.id}/'
        self.assertEqual(
            self.client.patch(url_detail, {'statut': 'RESOLU'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.post(f'{url_detail}changer-statut/', {'statut': 'EN_COURS'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.delete(url_detail).status_code,
            status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.get('/api/signalements/statistiques/').status_code,
            status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.get('/api/signalements/supervision/').status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.signalement.refresh_from_db()
        self.assertEqual(self.signalement.statut, Signalement.Statut.EN_ATTENTE)

    def test_responsable_municipal_full_supervision_access(self):
        """
        Le Responsable Municipal dispose d'un accès complet : changement de statut,
        statistiques avancées, vue de supervision avec IP émettrice et suppression.
        """
        self.client.force_authenticate(user=self.responsable)
        url_detail = f'/api/signalements/{self.signalement.id}/'

        # 1. Modification du statut via PATCH standard
        res_patch = self.client.patch(url_detail, {'statut': 'EN_COURS'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.json()['statut'], Signalement.Statut.EN_COURS)
        self.signalement.refresh_from_db()
        self.assertEqual(self.signalement.statut, Signalement.Statut.EN_COURS)

        # 2. Modification du statut via action dédiée /changer-statut/
        res_changer = self.client.post(
            f'{url_detail}changer-statut/',
            {'statut': 'RESOLU'},
            format='json'
        )
        self.assertEqual(res_changer.status_code, status.HTTP_200_OK)
        self.assertEqual(res_changer.json()['statut'], Signalement.Statut.RESOLU)
        self.signalement.refresh_from_db()
        self.assertEqual(self.signalement.statut, Signalement.Statut.RESOLU)

        # 3. Accès aux statistiques avancées
        res_stats = self.client.get('/api/signalements/statistiques/')
        self.assertEqual(res_stats.status_code, status.HTTP_200_OK)
        stats_data = res_stats.json()
        self.assertGreaterEqual(stats_data['total_signalements'], 1)
        self.assertIn('par_statut', stats_data)
        self.assertIn('conformite_inpdp', stats_data)
        self.assertEqual(stats_data['taux_resolution_pourcent'], 100.0)

        # 4. Accès au rapport global de supervision (incluant ip_emetteur)
        res_supervision = self.client.get('/api/signalements/supervision/')
        self.assertEqual(res_supervision.status_code, status.HTTP_200_OK)
        sup_data = res_supervision.json()
        self.assertGreaterEqual(sup_data['total'], 1)
        self.assertEqual(sup_data['signalements'][0]['ip_emetteur'], '196.200.10.50')

        # 5. Suppression autorisée pour le Responsable Municipal
        res_delete = self.client.delete(url_detail)
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Signalement.objects.filter(id=self.signalement.id).exists())

    def test_jwt_bearer_authentication_flow(self):
        """
        Vérifie l'authentification via /api/signalements/auth/login/ (JWT Bearer)
        et l'injection de l'en-tête Authorization: Bearer <token>.
        """
        # 1. Mauvais identifiants -> 401
        res_bad = self.client.post(
            '/api/signalements/auth/login/',
            {'username': 'responsable_mairie', 'password': 'WrongPassword'},
            format='json',
        )
        self.assertEqual(res_bad.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Connexion Citoyen -> token avec role=CITOYEN, bloqué (403) sur /statistiques/
        res_cit = self.client.post(
            '/api/signalements/auth/login/',
            {'username': 'citoyen_capbon', 'password': 'CitoyenPassword123!'},
            format='json',
        )
        self.assertEqual(res_cit.status_code, status.HTTP_200_OK)
        cit_token = res_cit.json()['access']
        self.assertEqual(res_cit.json()['user']['role'], UserRole.CITOYEN)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {cit_token}')
        self.assertEqual(
            self.client.get('/api/signalements/statistiques/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # 3. Connexion Responsable Municipal -> token Bearer accepté sur /auth/me/, /statistiques/, /changer-statut/
        self.client.credentials()  # reset
        res_resp = self.client.post(
            '/api/signalements/auth/login/',
            {'username': 'responsable_mairie', 'password': 'MairiePassword123!'},
            format='json',
        )
        self.assertEqual(res_resp.status_code, status.HTTP_200_OK)
        resp_data = res_resp.json()
        self.assertEqual(resp_data['user']['role'], UserRole.RESPONSABLE_MUNICIPAL)
        self.assertTrue(resp_data['user']['est_responsable_municipal'])

        resp_token = resp_data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp_token}')

        res_me = self.client.get('/api/signalements/auth/me/')
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)
        self.assertEqual(res_me.json()['username'], 'responsable_mairie')

        res_stats = self.client.get('/api/signalements/statistiques/')
        self.assertEqual(res_stats.status_code, status.HTTP_200_OK)

        res_statut = self.client.post(
            f'/api/signalements/{self.signalement.id}/changer-statut/',
            {'statut': 'EN_COURS'},
            format='json',
        )
        self.assertEqual(res_statut.status_code, status.HTTP_200_OK)
        self.assertEqual(res_statut.json()['statut'], Signalement.Statut.EN_COURS)

        # 4. Jeton invalide / falsifié -> 401 Unauthorized
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.jwt.token')
        res_tampered = self.client.get('/api/signalements/statistiques/')
        self.assertEqual(res_tampered.status_code, status.HTTP_401_UNAUTHORIZED)


class SignalementProtectionCivileSyncIntegrationTest(TestCase):
    """
    Tests d'intégration de la passerelle automatique Citoyen ➔ Protection Civile
    et de la synchronisation bidirectionnelle des statuts d'intervention.
    """

    def setUp(self):
        self.client = APIClient()
        cache.clear()

        # Responsable municipal authentifié pour les changements de statut
        self.responsable = User.objects.create_user(
            username='responsable_test_sync',
            password='TestSyncPass2026!'
        )
        self.responsable.profil.role = UserRole.RESPONSABLE_MUNICIPAL
        self.responsable.profil.save()

    def test_accident_signalement_automatically_creates_alerte_accident(self):
        """
        Un signalement citoyen de type ACCIDENT ou de gravité CRITIQUE doit créer
        automatiquement une AlerteAccident liée et un SignalementAccident.
        """
        payload = {
            'categorie': 'ACCIDENT',
            'gravite': 'CRITIQUE',
            'description': 'Collision frontale avenue des Martyrs avec blessés',
            'latitude': 36.8475,
            'longitude': 11.0939,
            'adresse_texte': 'Avenue des Martyrs, Kélibia',
            'quartier': 'Kélibia',
        }
        res = self.client.post('/api/signalements/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        sig_id = res.json()['id']
        signalement = Signalement.objects.get(id=sig_id)

        # 1. Vérification de la création et du lien de l'alerte
        self.assertIsNotNone(signalement.alerte_liee, "Le signalement d'accident doit être lié à une AlerteAccident.")
        alerte = signalement.alerte_liee

        # 2. Vérification des propriétés de l'alerte Protection Civile
        self.assertEqual(alerte.gravite, 'GRAVE')
        self.assertEqual(alerte.statut, 'CONFIRME')
        self.assertGreaterEqual(alerte.signalements_lies.count(), 1)
        self.assertAlmostEqual(alerte.latitude, 36.8475, places=3)
        self.assertAlmostEqual(alerte.longitude, 11.0939, places=3)

        # 3. Vérification de l'inscription au journal d'audit
        from urgences.models import JournalAudit
        audits = JournalAudit.objects.filter(alerte=alerte)
        self.assertTrue(audits.exists(), "Un journal d'audit doit être généré pour la Protection Civile.")

    def test_non_urgent_signalement_does_not_create_alerte(self):
        """
        Un signalement de voirie standard (déchets, faible gravité) ne doit PAS
        encombrer la Protection Civile ni créer d'AlerteAccident.
        """
        payload = {
            'categorie': 'DECHETS',
            'gravite': 'FAIBLE',
            'description': 'Poubelle débordante près du site archéologique',
            'latitude': 36.9467,
            'longitude': 11.0989,
            'quartier': 'Kerkouane',
        }
        res = self.client.post('/api/signalements/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        sig_id = res.json()['id']
        signalement = Signalement.objects.get(id=sig_id)
        self.assertIsNone(signalement.alerte_liee, "Un signalement standard ne doit pas être lié à une alerte d'urgence.")

    def test_bidirectional_sync_municipal_to_protection_civile(self):
        """
        Lorsque le Responsable Municipal met à jour le statut (EN_COURS puis RESOLU),
        l'alerte Protection Civile liée doit passer à PRISE_EN_CHARGE puis CLOTURE.
        """
        self.client.force_authenticate(user=self.responsable)

        # 1. Création d'un signalement d'accident
        signalement = Signalement.objects.create(
            categorie=Signalement.Categorie.ACCIDENT,
            gravite=Signalement.Gravite.ELEVEE,
            description="Véhicule en panne bloquant les voies",
            latitude=36.7361,
            longitude=10.9558,
            quartier="Menzel Horr",
        )
        self.assertIsNotNone(signalement.alerte_liee)
        alerte = signalement.alerte_liee

        # 2. Le Responsable Municipal passe le statut à EN_COURS
        url_changer = f'/api/signalements/{signalement.id}/changer-statut/'
        res_cours = self.client.post(url_changer, {'statut': 'EN_COURS'}, format='json')
        self.assertEqual(res_cours.status_code, status.HTTP_200_OK)

        alerte.refresh_from_db()
        self.assertEqual(
            alerte.statut,
            'PRISE_EN_CHARGE',
            "Le statut de l'alerte pompier doit être synchronisé vers PRISE_EN_CHARGE."
        )
        self.assertIsNotNone(alerte.date_prise_en_charge)

        # 3. Le Responsable Municipal passe le statut à RESOLU
        res_resolu = self.client.post(url_changer, {'statut': 'RESOLU'}, format='json')
        self.assertEqual(res_resolu.status_code, status.HTTP_200_OK)

        alerte.refresh_from_db()
        self.assertEqual(
            alerte.statut,
            'CLOTURE',
            "Le statut de l'alerte pompier doit être synchronisé vers CLOTURE."
        )
        self.assertIsNotNone(alerte.date_cloture)

    def test_bidirectional_sync_protection_civile_to_municipal(self):
        """
        Lorsque la Protection Civile prend en charge ou clôture une alerte,
        le Signalement municipal correspondant doit évoluer vers EN_COURS puis RESOLU.
        """
        signalement = Signalement.objects.create(
            categorie=Signalement.Categorie.ACCIDENT,
            gravite=Signalement.Gravite.CRITIQUE,
            description="Accident grave Route du Port de Kélibia",
            latitude=36.8475,
            longitude=11.0939,
            quartier="Kélibia",
        )
        alerte = signalement.alerte_liee
        self.assertIsNotNone(alerte)

        # 1. La Protection Civile change le statut de l'alerte vers EN_INTERVENTION
        alerte.statut = 'EN_INTERVENTION'
        alerte.save()

        signalement.refresh_from_db()
        self.assertEqual(
            signalement.statut,
            Signalement.Statut.EN_COURS,
            "Le signalement municipal doit être synchronisé vers EN_COURS."
        )

        # 2. La Protection Civile clôture l'alerte
        alerte.statut = 'CLOTURE'
        alerte.save()

        signalement.refresh_from_db()
        self.assertEqual(
            signalement.statut,
            Signalement.Statut.RESOLU,
            "Le signalement municipal doit être synchronisé vers RESOLU."
        )


class SignalementAntiAbuseAndCitizenTrackingTest(TestCase):
    """
    Tests unitaires pour le quota différencié (utilisateur authentifié vs IP anonyme),
    la détection anti-doublon spatio-temporelle (< 50 m, < 10 min),
    et le suivi citoyen (?mes_signalements=true & est_mon_signalement).
    """

    def setUp(self):
        self.client = APIClient()
        cache.clear()
        self.citoyen1 = User.objects.create_user(username='citoyen_quota_1', password='Pwd123!')
        self.citoyen2 = User.objects.create_user(username='citoyen_quota_2', password='Pwd123!')

    def test_anti_duplicate_spatial_temporal_blocks_non_accident(self):
        """
        Deux signalements de voirie de même catégorie à < 50 m et < 10 min
        doivent retourner HTTP 409 Conflict, tandis qu'à > 100 m ils sont acceptés.
        """
        payload_base = {
            'categorie': 'NID_DE_POULE',
            'gravite': 'MOYENNE',
            'description': 'Nid-de-poule profond avenue des Martyrs',
            'latitude': 36.8475,
            'longitude': 11.0939,
            'quartier': 'Kélibia',
        }
        res1 = self.client.post('/api/signalements/', payload_base, format='json', REMOTE_ADDR='196.10.20.30')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        first_id = res1.json()['id']

        # Doublon à ~14 mètres (< 50 m) dans les 10 minutes -> 409 Conflict
        payload_dup = {**payload_base, 'latitude': 36.8476, 'longitude': 11.0940}
        res_dup = self.client.post('/api/signalements/', payload_dup, format='json', REMOTE_ADDR='196.10.20.30')
        self.assertEqual(res_dup.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res_dup.json()['code'], 'DUPLICATE_REPORT')
        self.assertEqual(res_dup.json()['doublon_id'], first_id)

        # Signalement suffisamment éloigné (~150 m) -> 201 Created
        payload_far = {**payload_base, 'latitude': 36.8490, 'longitude': 11.0939}
        res_far = self.client.post('/api/signalements/', payload_far, format='json', REMOTE_ADDR='196.10.20.30')
        self.assertEqual(res_far.status_code, status.HTTP_201_CREATED)

    def test_differentiated_throttling_and_mes_signalements_filter(self):
        """
        Un citoyen authentifié dispose d'un quota propre (15/h) indépendant de l'IP partagée,
        et peut filtrer ses propres signalements sans exposer l'IP ou l'auteur d'autrui.
        """
        shared_ip = '196.200.99.1'

        # 1. citoyen1 crée 6 signalements espacés (> 50 m) depuis la même IP -> tous acceptés (quota 15/h > 5/h)
        self.client.force_authenticate(user=self.citoyen1)
        for i in range(6):
            res = self.client.post(
                '/api/signalements/',
                {
                    'categorie': 'ECLAIRAGE',
                    'gravite': 'FAIBLE',
                    'description': f'Lampadaire éteint #{i}',
                    'latitude': 36.8906 + (i * 0.002),
                    'longitude': 11.1197,
                    'quartier': 'Hammam El Ghezaz',
                },
                format='json',
                REMOTE_ADDR=shared_ip,
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 2. citoyen2 crée un signalement sur la même IP -> accepté & isolé
        self.client.force_authenticate(user=self.citoyen2)
        res_c2 = self.client.post(
            '/api/signalements/',
            {
                'categorie': 'DECHETS',
                'gravite': 'MOYENNE',
                'description': 'Conteneur plein',
                'latitude': 36.8260,
                'longitude': 11.0180,
                'quartier': 'Azmour',
            },
            format='json',
            REMOTE_ADDR=shared_ip,
        )
        self.assertEqual(res_c2.status_code, status.HTTP_201_CREATED)

        # 3. Vérification du suivi citoyen (?mes_signalements=true & est_mon_signalement)
        res_mine = self.client.get('/api/signalements/?mes_signalements=true')
        self.assertEqual(res_mine.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_mine.json()), 1)
        self.assertTrue(res_mine.json()[0]['est_mon_signalement'])
        self.assertNotIn('ip_emetteur', res_mine.json()[0])

        res_all = self.client.get('/api/signalements/')
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_all.json()), 7)
        mine_flags = [item['est_mon_signalement'] for item in res_all.json()]
        self.assertEqual(mine_flags.count(True), 1)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DashboardAnalyticsFilterAndAggregationTest(TestCase):
    """
    Tests d'intégration Phase 2 : filtrage multi-critères cohérent sur /signalements/,
    /statistiques/ et /dashboard-analytics/, heatmap pondérée et séries temporelles.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.responsable = User.objects.create_user(
            username='resp_phase2', password='Pwd!123456', email='resp2@capbon.tn'
        )
        self.responsable.profil.role = UserRole.RESPONSABLE_MUNICIPAL
        self.responsable.profil.save()
        self.citoyen = User.objects.create_user(
            username='cit_phase2', password='Pwd!123456', email='cit2@capbon.tn'
        )

        # Jeu de données varié en statuts, gravités, catégories, localités et dates
        self.s1 = Signalement.objects.create(
            categorie=Signalement.Categorie.NID_DE_POULE,
            gravite=Signalement.Gravite.CRITIQUE,
            statut=Signalement.Statut.EN_COURS,
            description='Chaussée affaissée El Haouaria',
            latitude=37.0500,
            longitude=11.0144,
            quartier='El Haouaria',
        )
        self.s2 = Signalement.objects.create(
            categorie=Signalement.Categorie.NID_DE_POULE,
            gravite=Signalement.Gravite.ELEVEE,
            statut=Signalement.Statut.CONFIRME,
            description='Trou profond route des Grottes El Haouaria',
            latitude=37.0510,
            longitude=11.0152,
            quartier='El Haouaria',
        )
        self.s3 = Signalement.objects.create(
            categorie=Signalement.Categorie.ECLAIRAGE,
            gravite=Signalement.Gravite.FAIBLE,
            statut=Signalement.Statut.RESOLU,
            description='Ampoule grillée Kélibia',
            latitude=36.8475,
            longitude=11.0939,
            quartier='Kélibia',
        )
        # Signalement ancien (> 12 jours) pour tester le filtre période 7j
        old_sig = Signalement.objects.create(
            categorie=Signalement.Categorie.DECHETS,
            gravite=Signalement.Gravite.CRITIQUE,
            statut=Signalement.Statut.EN_ATTENTE,
            description='Dépôt sauvage ancien Kélibia',
            latitude=36.8480,
            longitude=11.0942,
            quartier='Kélibia',
        )
        Signalement.objects.filter(pk=old_sig.pk).update(
            date_creation=timezone.now() - timedelta(days=12)
        )

    def test_statistiques_aggregations_and_rbac(self):
        # Citoyen interdit sur dashboard-analytics
        self.client.force_authenticate(user=self.citoyen)
        res_forbidden = self.client.get('/api/signalements/dashboard-analytics/')
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Responsable obtient KPIs, zones haute densité, heatmap et évolution en peu de requêtes
        self.client.force_authenticate(user=self.responsable)
        with CaptureQueriesContext(connection) as queries:
            res = self.client.get('/api/signalements/dashboard-analytics/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 6)
        data = res.json()

        self.assertEqual(data['total_signalements'], 4)
        self.assertEqual(data['chantiers_actifs'], 2)  # s1 EN_COURS + s2 CONFIRME
        self.assertEqual(data['incidents_en_attente'], 1)
        self.assertEqual(data['details_chantiers']['voirie_active'], 2)
        self.assertGreaterEqual(len(data['heatmap_points']), 4)
        self.assertEqual(len(data['heatmap_points'][0]), 3)  # [lat, lng, intensite]
        self.assertTrue(len(data['zones_haute_densite']) >= 1)
        self.assertTrue(len(data['evolution_temporelle']) >= 1)

    def test_filters_gravite_periode_and_quartier_sync(self):
        self.client.force_authenticate(user=self.responsable)

        # Filtre periode=7j doit exclure le signalement âgé de 12 jours
        res_7j_stats = self.client.get('/api/signalements/statistiques/?periode=7j')
        res_7j_list = self.client.get('/api/signalements/?periode=7j')
        self.assertEqual(res_7j_stats.status_code, status.HTTP_200_OK)
        self.assertEqual(res_7j_stats.json()['total_signalements'], 3)
        self.assertEqual(len(res_7j_list.json()), 3)

        # Filtre combiné gravite=CRITIQUE + periode=7j -> uniquement s1
        res_crit = self.client.get(
            '/api/signalements/statistiques/?periode=7j&gravite=CRITIQUE'
        )
        self.assertEqual(res_crit.status_code, status.HTTP_200_OK)
        self.assertEqual(res_crit.json()['total_signalements'], 1)
        self.assertEqual(res_crit.json()['chantiers_actifs'], 1)

        # Filtre par délégation
        res_kelibia = self.client.get(
            '/api/signalements/statistiques/?quartier=K%C3%A9libia'
        )
        self.assertEqual(res_kelibia.status_code, status.HTTP_200_OK)
        self.assertEqual(res_kelibia.json()['total_signalements'], 2)

    def test_responsable_can_delete_signalement_rbac(self):
        target_id = str(self.s3.id)

        # Anonyme refusé
        self.client.force_authenticate(user=None)
        res_anon = self.client.delete(f'/api/signalements/{target_id}/')
        self.assertIn(
            res_anon.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertTrue(Signalement.objects.filter(pk=target_id).exists())

        # Citoyen refusé (403)
        self.client.force_authenticate(user=self.citoyen)
        res_cit = self.client.delete(f'/api/signalements/{target_id}/')
        self.assertEqual(res_cit.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Signalement.objects.filter(pk=target_id).exists())

        # Responsable Municipal autorisé (204)
        self.client.force_authenticate(user=self.responsable)
        res_del = self.client.delete(f'/api/signalements/{target_id}/')
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Signalement.objects.filter(pk=target_id).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class IsolationForestAnomalyDetectionTest(TestCase):
    """
    Tests ML Phase 3 (IsolationForest) :
    - Aucun faux positif sur un incident isolé ou espacé.
    - Détection réelle d'une accumulation soudaine + déduplication.
    - RBAC et acquittement des anomalies via API.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.responsable = User.objects.create_user(
            username='resp_ml', password='Pwd!123456', email='resp_ml@capbon.tn'
        )
        self.responsable.profil.role = UserRole.RESPONSABLE_MUNICIPAL
        self.responsable.profil.save()
        self.citoyen = User.objects.create_user(
            username='cit_ml', password='Pwd!123456', email='cit_ml@capbon.tn'
        )

    def test_no_false_positive_on_isolated_or_sparse_reports(self):
        # 1. Incident isolé à Azmour (< 3)
        Signalement.objects.create(
            categorie=Signalement.Categorie.ECLAIRAGE,
            gravite=Signalement.Gravite.FAIBLE,
            description='Un lampadaire isolé en panne',
            latitude=36.8260,
            longitude=11.0180,
            quartier='Azmour',
        )
        res_single = evaluer_anomalie_zone('Azmour', Signalement.Categorie.ECLAIRAGE)
        self.assertIsNone(res_single)

        # 2. Deux signalements faibles dispersés à Dar Allouche (~1.5 km)
        Signalement.objects.create(
            categorie=Signalement.Categorie.DECHETS,
            gravite=Signalement.Gravite.FAIBLE,
            description='Bac débordant nord',
            latitude=36.9350,
            longitude=11.1050,
            quartier='Dar Allouche',
        )
        Signalement.objects.create(
            categorie=Signalement.Categorie.DECHETS,
            gravite=Signalement.Gravite.FAIBLE,
            description='Bac débordant sud',
            latitude=36.9485,
            longitude=11.1050,
            quartier='Dar Allouche',
        )
        res_sparse = evaluer_anomalie_zone('Dar Allouche', Signalement.Categorie.DECHETS)
        self.assertIsNone(res_sparse)
        self.assertEqual(AlerteAnomalie.objects.count(), 0)

    def test_burst_triggers_anomaly_deduplication_and_acknowledgment_api(self):
        # 5 signalements rapprochés et graves à Hammam El Ghezaz -> pic anormal
        for idx in range(5):
            Signalement.objects.create(
                categorie=Signalement.Categorie.NID_DE_POULE,
                gravite=Signalement.Gravite.CRITIQUE if idx < 3 else Signalement.Gravite.ELEVEE,
                description=f'Effondrement chaussée burst #{idx}',
                latitude=36.8906 + (idx * 0.0002),
                longitude=11.1197 + (idx * 0.0002),
                quartier='Hammam El Ghezaz',
            )

        active_alerts = AlerteAnomalie.objects.filter(
            quartier='Hammam El Ghezaz',
            categorie=Signalement.Categorie.NID_DE_POULE,
            statut=AlerteAnomalie.Statut.ACTIVE,
        )
        self.assertEqual(active_alerts.count(), 1)
        alerte = active_alerts.first()
        self.assertEqual(alerte.nb_signalements, 5)
        self.assertGreater(alerte.score_anomalie, 50.0)

        # Un 6e signalement met à jour l'alerte existante sans la dupliquer
        Signalement.objects.create(
            categorie=Signalement.Categorie.NID_DE_POULE,
            gravite=Signalement.Gravite.CRITIQUE,
            description='Effondrement chaussée burst #6',
            latitude=36.8910,
            longitude=11.1201,
            quartier='Hammam El Ghezaz',
        )
        self.assertEqual(active_alerts.count(), 1)
        alerte.refresh_from_db()
        self.assertEqual(alerte.nb_signalements, 6)

        # RBAC Citoyen bloqué (403)
        self.client.force_authenticate(user=self.citoyen)
        self.assertEqual(
            self.client.get('/api/signalements/anomalies/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post('/api/signalements/anomalies/analyser/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                f'/api/signalements/anomalies/{alerte.id}/acquitter/'
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Responsable liste, scanne et acquitte l'anomalie
        self.client.force_authenticate(user=self.responsable)
        res_list = self.client.get('/api/signalements/anomalies/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_list.json()['total_actives'], 1)

        detectees = scanner_toutes_anomalies(fenetre_heures=6)
        self.assertTrue(any(d['quartier'] == 'Hammam El Ghezaz' for d in detectees))

        res_ack = self.client.post(
            f'/api/signalements/anomalies/{alerte.id}/acquitter/'
        )
        self.assertEqual(res_ack.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ack.json()['statut'], 'ACQUITTEE')
        self.assertEqual(res_ack.json()['acquittee_par_username'], 'resp_ml')

    def test_simulate_anomaly_burst_endpoint_rbac_and_isolation_forest(self):
        # 1. Citoyen bloqué (403 Forbidden) et aucune donnée créée
        self.client.force_authenticate(user=self.citoyen)
        res_forbidden = self.client.post('/api/signalements/anomalies/simuler/')
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Signalement.objects.count(), 0)
        self.assertEqual(AlerteAnomalie.objects.count(), 0)

        # 2. Responsable Municipal déclenche la simulation en 1 clic
        self.client.force_authenticate(user=self.responsable)
        res = self.client.post('/api/signalements/anomalies/simuler/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()

        self.assertEqual(len(data['signalements_generes']), 3)
        self.assertEqual(Signalement.objects.count(), 3)
        self.assertIsNotNone(data['alerte'])
        self.assertEqual(data['alerte']['statut'], AlerteAnomalie.Statut.ACTIVE)
        self.assertGreaterEqual(data['alerte']['nb_signalements'], 3)
        self.assertGreater(data['alerte']['score_anomalie'], 50.0)
        self.assertTrue(
            AlerteAnomalie.objects.filter(
                pk=data['alerte']['id'],
                statut=AlerteAnomalie.Statut.ACTIVE,
            ).exists()
        )





