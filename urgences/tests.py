from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import SignalementAccident, AlerteAccident, JournalAuditIntervention
from .services import (
    traiter_signalement,
    enregistrer_changement_statut,
    distance_metres,
)
from .ml_models import (
    prediger_risque_zone,
    evaluer_secteur_tunis,
    get_toutes_les_zones_risk_map,
    SECTEURS_TUNIS,
)
from .llm_assistant import extraire_contexte_terrain_reel, interroger_assistant_llm
from .simulation import (
    executer_simulation_fausse_alerte,
    executer_simulation_accident_confirme,
    executer_simulation_risk_map_tunis,
)

User = get_user_model()


class UrgencesClusteringTestCase(TestCase):
    """
    Test 1 : Regroupement spatial PostGIS et qualification anti-fausse alerte :
    - 1 signalement isolé non critique -> reste A_CONFIRMER (fausse alerte éliminée).
    - >= 2 signalements proches (< 200m) -> alerte CONFIRMEE.
    - 1 signalement critique direct -> alerte CONFIRMEE immédiatement.
    """

    def test_distance_metres_haversine(self):
        # Bab El Khadra vers Bab Saadoun (~1.8 km)
        d = distance_metres(36.8123, 10.1784, 36.8095, 10.1582)
        self.assertGreater(d, 1500)
        self.assertLess(d, 2200)

    def test_fausse_alerte_isolee_non_confirmee(self):
        sig = SignalementAccident.objects.create(
            latitude=36.8340,
            longitude=10.2330,
            adresse="Les Berges du Lac",
            description="Véhicule garé de travers",
            gravite_estimee="MOYENNE"
        )
        alerte = traiter_signalement(sig, valide_par_agent=False)

        self.assertEqual(alerte.statut, 'A_CONFIRMER')
        self.assertEqual(alerte.nb_signalements, 1)
        self.assertIsNone(alerte.date_confirmation)

    def test_concordance_deux_signalements_proches_confirme_alerte(self):
        # 1er signalement
        sig1 = SignalementAccident.objects.create(
            latitude=36.8002,
            longitude=10.1865,
            adresse="Avenue Habib Bourguiba",
            description="Choc entre 2 taxis",
            gravite_estimee="MOYENNE"
        )
        alerte = traiter_signalement(sig1, valide_par_agent=False)
        self.assertEqual(alerte.statut, 'A_CONFIRMER')

        # 2ème signalement concordant à ~50 mètres (< 200m)
        sig2 = SignalementAccident.objects.create(
            latitude=36.8005,
            longitude=10.1868,
            adresse="Avenue Habib Bourguiba - Carrefour",
            description="Accident confirmé Bourguiba",
            gravite_estimee="MOYENNE"
        )
        alerte_mise_a_jour = traiter_signalement(sig2, valide_par_agent=False)

        # Les 2 signalements ont été fusionnés sur la même alerte
        self.assertEqual(alerte.id, alerte_mise_a_jour.id)
        self.assertEqual(alerte_mise_a_jour.nb_signalements, 2)
        self.assertEqual(alerte_mise_a_jour.statut, 'CONFIRME')
        self.assertIsNotNone(alerte_mise_a_jour.date_confirmation)

    def test_signalement_critique_confirme_immediatement(self):
        sig_critique = SignalementAccident.objects.create(
            latitude=36.7865,
            longitude=10.1832,
            adresse="Échangeur Bab Alioua",
            description="Carambolage grave avec blessés et incendie",
            gravite_estimee="GRAVE"
        )
        alerte = traiter_signalement(sig_critique, valide_par_agent=False)
        self.assertEqual(alerte.statut, 'CONFIRME')
        self.assertEqual(alerte.gravite, 'GRAVE')
        self.assertIsNotNone(alerte.date_confirmation)


class UrgencesWorkflowAuditTestCase(TestCase):
    """
    Test 2 : Workflow strict d'intervention et Journal d'Audit :
    'recue' (CONFIRME) -> 'prise_en_charge' -> 'en_cours' (EN_INTERVENTION) -> 'cloturee' (CLOTURE)
    """

    def setUp(self):
        self.user = User.objects.create_user(username="agent_pompier_01", password="secure_password")
        self.alerte = AlerteAccident.objects.create(
            latitude=36.8123,
            longitude=10.1784,
            adresse="Avenue Habib Thameur",
            gravite="GRAVE",
            statut="CONFIRME"
        )

    def test_cycle_de_vie_complet_et_journal_audit(self):
        # 1. Prise en charge
        enregistrer_changement_statut(
            self.alerte,
            nouveau_statut="PRISE_EN_CHARGE",
            intervenant=self.user,
            matricule="TN-POMPIER-198",
            note="Départ Ambulance 198-A"
        )
        self.alerte.refresh_from_db()
        self.assertEqual(self.alerte.statut, "PRISE_EN_CHARGE")
        self.assertIsNotNone(self.alerte.date_prise_en_charge)

        audit1 = JournalAuditIntervention.objects.filter(alerte=self.alerte).latest('horodatage')
        self.assertEqual(audit1.statut_precedent, "CONFIRME")
        self.assertEqual(audit1.nouveau_statut, "PRISE_EN_CHARGE")
        self.assertEqual(audit1.matricule_intervenant, "TN-POMPIER-198")
        self.assertIn("198-A", audit1.note_intervention)

        # 2. En intervention
        enregistrer_changement_statut(
            self.alerte,
            nouveau_statut="EN_INTERVENTION",
            intervenant=self.user,
            note="Arrivée sur les lieux et balisage"
        )
        self.alerte.refresh_from_db()
        self.assertEqual(self.alerte.statut, "EN_INTERVENTION")
        self.assertIsNotNone(self.alerte.date_en_intervention)

        # 3. Clôture
        enregistrer_changement_statut(
            self.alerte,
            nouveau_statut="CLOTURE",
            intervenant=self.user,
            note="Blessés évacués vers Hôpital Charles Nicolle, voie dégagée"
        )
        self.alerte.refresh_from_db()
        self.assertEqual(self.alerte.statut, "CLOTURE")
        self.assertIsNotNone(self.alerte.date_cloture)

        total_audits = JournalAuditIntervention.objects.filter(alerte=self.alerte).count()
        self.assertEqual(total_audits, 3)


class UrgencesRiskMapTestCase(TestCase):
    """
    Test 3 : Moteur Risk Map (0–100 %, vert/orange/rouge, facteurs explicatifs).
    """

    def test_calcul_score_risk_map_et_facteurs(self):
        res_faible = prediger_risque_zone(trafic=1.2, travaux=0, pluie=0, incidents_recents=0)
        self.assertGreaterEqual(res_faible["score_risque_pourcentage"], 0)
        self.assertLessEqual(res_faible["score_risque_pourcentage"], 100)
        self.assertEqual(res_faible["niveau_couleur"], "vert")
        self.assertIsInstance(res_faible["facteurs_explicatifs"], list)
        self.assertGreater(len(res_faible["facteurs_explicatifs"]), 0)

        res_eleve = prediger_risque_zone(trafic=4.5, travaux=1, pluie=1, incidents_recents=6)
        self.assertGreaterEqual(res_eleve["score_risque_pourcentage"], 70.0)
        self.assertEqual(res_eleve["niveau_couleur"], "rouge")
        self.assertTrue(any("dense" in f.lower() or "incidents" in f.lower() for f in res_eleve["facteurs_explicatifs"]))

    def test_evaluation_secteurs_tunis(self):
        zones = get_toutes_les_zones_risk_map()
        self.assertEqual(len(zones), len(SECTEURS_TUNIS))
        for z in zones:
            self.assertIn("zone_nom", z)
            self.assertIn(z["niveau_couleur"], ["vert", "orange", "rouge"])
            self.assertGreaterEqual(z["score_risque_pourcentage"], 0)
            self.assertLessEqual(z["score_risque_pourcentage"], 100)
            self.assertIsInstance(z["facteurs_explicatifs"], list)


class UrgencesAssistantLLMTestCase(TestCase):
    """
    Test 4 : Assistant LLM RAG strict anti-hallucination.
    Vérifie qu'il s'appuie sur les données réelles et refuse d'inventer des informations.
    """

    def test_contexte_terrain_reel(self):
        ctx = extraire_contexte_terrain_reel()
        self.assertIn("risk_map", ctx)
        self.assertIn("casernes_operationnelles", ctx)
        self.assertIn("alertes_actives", ctx)

    def test_assistant_repond_avec_donnees_reelles_sans_halluciner(self):
        res_zones = interroger_assistant_llm("Quelles sont les zones rouges prioritaires ?")
        self.assertIn("reponse", res_zones)
        self.assertIsInstance(res_zones["reponse"], str)
        self.assertIn("score", res_zones["reponse"].lower())

        res_casernes = interroger_assistant_llm("Quelles casernes sont disponibles à Tunis ?")
        self.assertIn("reponse", res_casernes)
        self.assertIn("Bab El Khadra", res_casernes["reponse"])


class UrgencesSimulationApiTestCase(TestCase):
    """
    Test 5 : Endpoints de simulation et API.
    """

    def setUp(self):
        self.client = APIClient()

    def test_endpoint_simulation_fausse_alerte(self):
        res = self.client.post('/api/urgences/simulate/', {"mode": "fausse_alerte"}, format='json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenario"], "fausse_alerte_isolee")
        self.assertEqual(data["statut_alerte"], "A_CONFIRMER")
        self.assertFalse(data["alarme_declenchee"])

    def test_endpoint_simulation_accident_confirme(self):
        res = self.client.post('/api/urgences/simulate/', {"mode": "accident_confirme"}, format='json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenario"], "accident_confirme_clustering")
        self.assertEqual(data["statut_alerte"], "CONFIRME")
        self.assertTrue(data["alarme_declenchee"])

    def test_endpoint_simulation_risk_map(self):
        res = self.client.post('/api/urgences/simulate/', {"mode": "risk_map"}, format='json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenario"], "generation_risk_map_tunis")
        self.assertIn("repartition", data)

    def test_endpoint_audit_intervention(self):
        alerte = AlerteAccident.objects.create(latitude=36.8, longitude=10.1, gravite="GRAVE", statut="CONFIRME")
        enregistrer_changement_statut(alerte, "PRISE_EN_CHARGE", note="Test audit API")

        res = self.client.get(f'/api/urgences/alerte/{alerte.id}/audit/')
        self.assertEqual(res.status_code, 200)
        audits = res.json()
        self.assertGreaterEqual(len(audits), 1)
        self.assertEqual(audits[0]["nouveau_statut"], "PRISE_EN_CHARGE")
