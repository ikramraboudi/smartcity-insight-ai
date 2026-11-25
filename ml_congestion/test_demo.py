"""
Script de Démonstration & Validation du Module D (Prédiction de Congestion)
Exécute les 3 fonctionnalités du cahier des charges et affiche les métriques d'évaluation.
"""

import json
import os
from .predictor import (
    predict_congestion_by_street,
    estimate_worksite_impact,
    recommend_alternative_routes,
    load_trained_models,
)


def run_demonstration():
    print("=" * 80)
    print("   🚦 SMARTCITY INSIGHT AI — MODULE D : PRÉDICTION DE CONGESTION (ML)   ")
    print("   Cahier des charges : Sections 7.4 (Fonctionnalités) & 8 (Machine Learning) ")
    print("=" * 80)

    # 1. Chargement et vérification des modèles
    print("\n📦 [1/4] CHARGEMENT DES MODÈLES ENTRAÎNÉS...")
    load_trained_models()

    report_path = "ml_congestion/reports/model_evaluation.json"
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        print("\n📈 [2/4] MÉTRIQUES D'ÉVALUATION SUR JEU DE TEST CHRONOLOGIQUE (Section 8.5) :")
        print(f"   • Période d'entraînement : {metrics['chronological_split']['train_period']}")
        print(f"   • Période de test       : {metrics['chronological_split']['test_period']}")
        print(f"   • Échantillons test     : {metrics['test_samples']}")

        print("\n   A. RÉGRESSION (Indice de congestion 1.0 à 5.0) :")
        for model_name, res in metrics["regression_comparison"].items():
            best_tag = " 🏆 (RETENU)" if model_name == metrics["best_regression_model"] else ""
            print(f"      - {model_name:<30} ➔ MAE: {res['MAE']} | RMSE: {res['RMSE']} | R²: {res['R2']}{best_tag}")

        print("\n   B. CLASSIFICATION (Classes FLUIDE / MODÉRÉ / ÉLEVÉ / CRITIQUE) :")
        for model_name, res in metrics["classification_comparison"].items():
            best_tag = " 🏆 (RETENU)" if model_name == metrics["best_classification_model"] else ""
            print(f"      - {model_name:<30} ➔ F1: {res['F1_Score']*100:.1f}% | Précision: {res['Precision']*100:.1f}% | Rappel: {res['Recall']*100:.1f}%{best_tag}")

        print("\n   C. VARIABLES EXPLICATIVES LES PLUS INFLUENTES (Feature Importance 8.4) :")
        for idx, item in enumerate(metrics["feature_importances"][:5], 1):
            print(f"      {idx}. {item['feature']:<30} : {item['importance']*100:.1f}%")

    # 2. Test Fonction 1 : Prédiction par rue et créneau horaire
    test_dt = "2026-11-23T08:30:00"  # Lundi 08h30 (Heure de pointe matinale)
    print("\n" + "=" * 80)
    print(f"🔍 [3/4] TEST FONCTION 1 : RISQUE DE CONGESTION PAR RUE & CRÉNEAU ({test_dt})")
    print("=" * 80)

    predictions = predict_congestion_by_street(
        simulation_datetime=test_dt,
        chantiers=["seg_menzel_horr_mc27"],
        meteo_pluie=1,  # Simulation par temps de pluie
    )

    print(f"{'ARTÈRE ROUTIÈRE':<46} | {'INDICE':<6} | {'RISQUE':<8} | {'STATUT':<10} | {'VITESSE':<10} | {'RETARD'}")
    print("-" * 95)
    for p in predictions:
        work_flag = " 🚧" if p["has_worksite"] else ""
        print(
            f"{p['street_name'][:44] + work_flag:<46} | "
            f"{p['congestion_index']:<6.2f} | "
            f"{p['congestion_risk_pct']:>5.1f}% | "
            f"{p['congestion_class']:<10} | "
            f"{p['estimated_speed_kmh']:>4.1f} km/h | "
            f"+{p['estimated_delay_min']:.1f} min"
        )

    # 3. Test Fonction 2 : Estimation de l'impact d'un chantier
    print("\n" + "=" * 80)
    print("🚧 [4/4] TEST FONCTION 2 : ESTIMATION DE L'IMPACT D'UN CHANTIER SUR LA CIRCULATION")
    print("=" * 80)

    impact = estimate_worksite_impact(
        street_id="seg_menzel_horr_mc27",
        simulation_datetime=test_dt,
        meteo_pluie=1,
    )

    print(f"Artère analysée : {impact['street_name']}")
    print(f"Créneau analysé : {impact['simulation_datetime']}")
    print("\n• Condition de référence (SANS chantier) :")
    print(f"   ➔ Risque : {impact['baseline_without_worksite']['congestion_risk_pct']}% ({impact['baseline_without_worksite']['congestion_class']}) | Vitesse : {impact['baseline_without_worksite']['estimated_speed_kmh']} km/h")
    print("• Condition avec chantier actif (AVEC travaux) :")
    print(f"   ➔ Risque : {impact['with_worksite']['congestion_risk_pct']}% ({impact['with_worksite']['congestion_class']}) | Vitesse : {impact['with_worksite']['estimated_speed_kmh']} km/h")
    print("\n📊 SURCROÎT PROVOQUÉ PAR LE CHANTIER (Δ) :")
    print(f"   ➔ Surcroît de risque de congestion : {impact['worksite_impact_delta']['delta_risk_pct']}")
    print(f"   ➔ Retard additionnel estimé        : {impact['worksite_impact_delta']['additional_delay_minutes']}")
    print(f"   ➔ Chute de vitesse moyenne         : {impact['worksite_impact_delta']['speed_drop_kmh']}")
    print(f"   ➔ Niveau d'impact                 : {impact['worksite_impact_delta']['impact_level']}")
    print(f"\n💡 Interprétation : {impact['interpretation']}")

    # 4. Test Fonction 3 : Recommandation d'itinéraires alternatifs
    print("\n" + "=" * 80)
    print("🧭 TEST FONCTION 3 : RECOMMANDATION D'ITINÉRAIRES ALTERNATIFS")
    print("=" * 80)

    alt_rec = recommend_alternative_routes(
        street_id="seg_menzel_horr_mc27",
        simulation_datetime=test_dt,
        chantiers=["seg_menzel_horr_mc27"],
        meteo_pluie=1,
    )

    print(f"Artère saturée demandée : {alt_rec['analyzed_street']['street_name']}")
    print(f"Risque constaté         : {alt_rec['analyzed_street']['congestion_risk_pct']}% ({alt_rec['analyzed_street']['congestion_class']})")
    print(f"\n📢 Recommandation du modèle ML :")
    print(f"   {alt_rec['recommendation_summary']}")

    if alt_rec["recommended_alternative"]:
        rec = alt_rec["recommended_alternative"]
        print(f"\n✅ Itinéraire de délestage sélectionné :")
        print(f"   • Nom de l'artère de secours : {rec['street_name']}")
        print(f"   • Risque sur cette artère    : {rec['congestion_risk_pct']}% ({rec['congestion_class']})")
        print(f"   • Vitesse estimée            : {rec['estimated_speed_kmh']} km/h")
        print(f"   • Gain de temps estimé       : ~{alt_rec['estimated_time_saved_min']} minutes")

    print("\n" + "=" * 80)
    print("✨ DÉMONSTRATION COMPLÈTE DU MODULE D TERMINÉE AVEC SUCCÈS")
    print("=" * 80)


if __name__ == "__main__":
    run_demonstration()
