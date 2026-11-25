"""
Tests unitaires pour le Module D — Prédiction de Congestion.
Vérifie le respect des sections 7.4 et 8 du cahier des charges.
"""

from django.test import TestCase
from rest_framework.test import APIClient
from .predictor import (
    predict_congestion_by_street,
    estimate_worksite_impact,
    recommend_alternative_routes,
    load_trained_models,
)
from .data_pipeline import CAP_BON_STREETS


class ModuleDCongestionMLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_trained_models()
        cls.client = APIClient()

    def test_predict_congestion_by_street_format(self):
        """Vérifie que la prédiction par rue renvoie l'indicateur précis pour les axes du Nord-Est Cap Bon."""
        dt = "2026-11-23T08:30:00"  # Lundi 08h30 (Pointe matin)
        preds = predict_congestion_by_street(simulation_datetime=dt, chantiers=[], meteo_pluie=0)

        self.assertEqual(len(preds), len(CAP_BON_STREETS))
        for p in preds:
            self.assertIn("street_id", p)
            self.assertIn("congestion_index", p)
            self.assertIn("congestion_risk_pct", p)
            self.assertIn("congestion_class", p)
            self.assertIn("color", p)
            self.assertIn("estimated_speed_kmh", p)
            # Vérification des bornes de l'indicateur précis
            self.assertGreaterEqual(p["congestion_index"], 1.0)
            self.assertLessEqual(p["congestion_index"], 5.0)
            self.assertGreaterEqual(p["congestion_risk_pct"], 0.0)
            self.assertLessEqual(p["congestion_risk_pct"], 100.0)
            self.assertIn(p["congestion_class"], ["FLUIDE", "MODERE", "ELEVE", "CRITIQUE"])

    def test_estimate_worksite_impact_delta(self):
        """Vérifie que l'impact d'un chantier calcule bien le surcroît de risque (Δ)."""
        dt = "2026-11-23T08:30:00"
        impact = estimate_worksite_impact(
            street_id="seg_menzel_horr_mc27",
            simulation_datetime=dt,
            meteo_pluie=0,
        )

        self.assertIn("baseline_without_worksite", impact)
        self.assertIn("with_worksite", impact)
        self.assertIn("worksite_impact_delta", impact)

        base_idx = impact["baseline_without_worksite"]["congestion_index"]
        work_idx = impact["with_worksite"]["congestion_index"]
        # Un chantier actif doit augmenter ou égaler l'indice de congestion
        self.assertGreaterEqual(work_idx, base_idx)

    def test_recommend_alternative_routes(self):
        """Vérifie la recommandation d'itinéraires alternatifs lors d'une forte congestion."""
        dt = "2026-11-23T08:30:00"
        rec = recommend_alternative_routes(
            street_id="seg_menzel_horr_mc27",
            simulation_datetime=dt,
            chantiers=["seg_menzel_horr_mc27"],
            meteo_pluie=1,
        )

        self.assertIn("analyzed_street", rec)
        self.assertIn("is_congested", rec)
        self.assertIn("recommendation_summary", rec)
        self.assertTrue(rec["is_congested"])
        self.assertIsNotNone(rec["recommended_alternative"])

    def test_api_predict_endpoint(self):
        """Vérifie le bon fonctionnement de l'endpoint REST /api/ml/congestion/predict/."""
        response = self.client.post(
            "/api/ml/congestion/predict/",
            data={
                "simulation_datetime": "2026-11-23T08:30:00",
                "chantiers": ["seg_menzel_horr_mc27"],
                "meteo_pluie": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["predictions"]), len(CAP_BON_STREETS))
        self.assertEqual(len(data["worksite_impacts"]), 1)

    def test_api_metrics_endpoint(self):
        """Vérifie l'exposition des métriques d'évaluation via /api/ml/congestion/metrics/."""
        response = self.client.get("/api/ml/congestion/metrics/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("regression_comparison", data)
        self.assertIn("classification_comparison", data)
        self.assertIn("feature_importances", data)
