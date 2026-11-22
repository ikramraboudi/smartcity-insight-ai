"""
Module D — Entraînement et Évaluation des Modèles (Sections 8.3 & 8.5)
Algorithmes : Random Forest vs Gradient Boosting.
Découpage chronologique strict, calcul des métriques (MAE, RMSE, F1-score)
et sauvegarde des modèles optimaux.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data_pipeline import load_dataset

# Définition des variables explicatives (Section 8.4)
CATEGORICAL_FEATURES = ["street_id", "road_type", "creneau_horaire"]
NUMERICAL_FEATURES = [
    "hour",
    "minute",
    "day_of_week",
    "is_weekend",
    "is_rush_hour",
    "base_speed_kmh",
    "length_km",
    "proximity_sensitive",
    "presence_travaux",
    "meteo_pluie",
    "incidents_recents",
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERICAL_FEATURES


def get_preprocessor() -> ColumnTransformer:
    """Crée le pipeline de prétraitement avec OneHotEncoder et StandardScaler."""
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERICAL_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )


def train_and_evaluate_models(
    csv_path: str = "ml_congestion/data/traffic_historical_dataset.csv",
    models_dir: str = "ml_congestion/models",
    reports_dir: str = "ml_congestion/reports",
) -> Dict[str, Any]:
    """
    Entraîne et compare Random Forest et Gradient Boosting avec séparation chronologique.
    Sauvegarde le modèle gagnant et exporte le rapport de métriques.
    """
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    print("=" * 70)
    print("🚦 SMARTCITY INSIGHT AI — MODULE D : ENTRAÎNEMENT DU MODÈLE DE CONGESTION")
    print("=" * 70)

    # 1. Chargement des données
    df = load_dataset(csv_path)
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    X = df[ALL_FEATURES]
    y_reg = df["congestion_index"]       # Cible continue (1.0 à 5.0)
    y_clf = df["congestion_class"]       # Cible discrète (FLUIDE, MODERE, ELEVE, CRITIQUE)

    # 2. Séparation chronologique stricte (Section 8.5)
    split_idx = int(len(df) * 0.80)
    train_end_date = df.iloc[split_idx - 1]["date"]
    test_start_date = df.iloc[split_idx]["date"]

    print(f"\n📅 Séparation chronologique :")
    print(f"   • Train ({split_idx} échantillons) : du {df.iloc[0]['date']} au {train_end_date}")
    print(f"   • Test  ({len(df) - split_idx} échantillons) : du {test_start_date} au {df.iloc[-1]['date']}")

    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_reg_train, y_reg_test = y_reg.iloc[:split_idx], y_reg.iloc[split_idx:]
    y_clf_train, y_clf_test = y_clf.iloc[:split_idx], y_clf.iloc[split_idx:]

    # 3. Entraînement et Comparaison Régression (Indice de Congestion)
    print("\n" + "-" * 70)
    print("⚙️ 1. MODÈLES DE RÉGRESSION (Prédiction de l'indice de 1.0 à 5.0)")
    print("-" * 70)

    reg_models = {
        "Random Forest Regressor": Pipeline([
            ("prep", get_preprocessor()),
            ("model", RandomForestRegressor(n_estimators=80, max_depth=16, random_state=42, n_jobs=-1))
        ]),
        "Gradient Boosting Regressor": Pipeline([
            ("prep", get_preprocessor()),
            ("model", GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42))
        ]),
    }

    reg_results = {}
    best_reg_name = None
    best_reg_mae = float("inf")
    best_reg_pipeline = None

    for name, pipe in reg_models.items():
        t0 = time.time()
        pipe.fit(X_train, y_reg_train)
        train_time = round(time.time() - t0, 2)

        preds = pipe.predict(X_test)
        mae = float(mean_absolute_error(y_reg_test, preds))
        rmse = float(np.sqrt(mean_squared_error(y_reg_test, preds)))
        r2 = float(r2_score(y_reg_test, preds))

        reg_results[name] = {
            "MAE": round(mae, 4),
            "RMSE": round(rmse, 4),
            "R2": round(r2, 4),
            "train_time_sec": train_time,
        }

        print(f"   [{name}]")
        print(f"      ➔ MAE  : {mae:.4f} (écart moyen d'indice)")
        print(f"      ➔ RMSE : {rmse:.4f}")
        print(f"      ➔ R²   : {r2:.4f}")
        print(f"      ➔ Temps: {train_time}s")

        if mae < best_reg_mae:
            best_reg_mae = mae
            best_reg_name = name
            best_reg_pipeline = pipe

    print(f"\n🏆 Meilleur modèle de régression sélectionné : {best_reg_name} (MAE = {best_reg_mae:.4f})")

    # 4. Entraînement et Comparaison Classification (Classe de Congestion)
    print("\n" + "-" * 70)
    print("⚙️ 2. MODÈLES DE CLASSIFICATION (FLUIDE, MODERE, ELEVE, CRITIQUE)")
    print("-" * 70)

    clf_models = {
        "Random Forest Classifier": Pipeline([
            ("prep", get_preprocessor()),
            ("model", RandomForestClassifier(n_estimators=80, max_depth=16, random_state=42, n_jobs=-1))
        ]),
        "Gradient Boosting Classifier": Pipeline([
            ("prep", get_preprocessor()),
            ("model", GradientBoostingClassifier(n_estimators=80, max_depth=4, learning_rate=0.1, random_state=42))
        ]),
    }

    clf_results = {}
    best_clf_name = None
    best_clf_f1 = -1.0
    best_clf_pipeline = None

    for name, pipe in clf_models.items():
        t0 = time.time()
        pipe.fit(X_train, y_clf_train)
        train_time = round(time.time() - t0, 2)

        preds = pipe.predict(X_test)
        acc = float(accuracy_score(y_clf_test, preds))
        prec = float(precision_score(y_clf_test, preds, average="weighted", zero_division=0))
        rec = float(recall_score(y_clf_test, preds, average="weighted", zero_division=0))
        f1 = float(f1_score(y_clf_test, preds, average="weighted", zero_division=0))

        clf_results[name] = {
            "Accuracy": round(acc, 4),
            "Precision": round(prec, 4),
            "Recall": round(rec, 4),
            "F1_Score": round(f1, 4),
            "train_time_sec": train_time,
        }

        print(f"   [{name}]")
        print(f"      ➔ Précision : {prec * 100:.2f}%")
        print(f"      ➔ Rappel    : {rec * 100:.2f}%")
        print(f"      ➔ F1-Score  : {f1 * 100:.2f}%")
        print(f"      ➔ Accuracy  : {acc * 100:.2f}%")

        if f1 > best_clf_f1:
            best_clf_f1 = f1
            best_clf_name = name
            best_clf_pipeline = pipe

    print(f"\n🏆 Meilleur modèle de classification sélectionné : {best_clf_name} (F1 = {best_clf_f1 * 100:.2f}%)")

    # 5. Extraction de l'importance des variables
    feature_names = (
        NUMERICAL_FEATURES
        + list(
            best_reg_pipeline.named_steps["prep"]
            .named_transformers_["cat"]
            .get_feature_names_out(CATEGORICAL_FEATURES)
        )
    )
    importances = best_reg_pipeline.named_steps["model"].feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    feature_importance_ranking = [
        {"feature": feature_names[i], "importance": round(float(importances[i]), 4)}
        for i in sorted_idx[:12]
    ]

    print("\n" + "-" * 70)
    print("🔍 TOP VARIABLES EXPLICATIVES LES PLUS INFLUENTES (Section 8.4) :")
    print("-" * 70)
    for idx, item in enumerate(feature_importance_ranking[:6], 1):
        print(f"   {idx}. {item['feature']:<30} : {item['importance'] * 100:.2f}%")

    # 6. Sauvegarde des pipelines et du rapport d'évaluation
    reg_path = os.path.join(models_dir, "best_congestion_regressor.joblib")
    clf_path = os.path.join(models_dir, "best_congestion_classifier.joblib")
    joblib.dump(best_reg_pipeline, reg_path)
    joblib.dump(best_clf_pipeline, clf_path)

    report = {
        "evaluation_timestamp": datetime.now().isoformat(),
        "train_samples": split_idx,
        "test_samples": len(df) - split_idx,
        "chronological_split": {
            "train_period": f"{df.iloc[0]['date']} -> {train_end_date}",
            "test_period": f"{test_start_date} -> {df.iloc[-1]['date']}",
        },
        "regression_comparison": reg_results,
        "best_regression_model": best_reg_name,
        "classification_comparison": clf_results,
        "best_classification_model": best_clf_name,
        "feature_importances": feature_importance_ranking,
    }

    report_path = os.path.join(reports_dir, "model_evaluation.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f"💾 Modèles sauvegardés avec succès dans : {models_dir}")
    print(f"📄 Rapport d'évaluation JSON sauvegardé : {report_path}")
    print("=" * 70)

    return report


if __name__ == "__main__":
    train_and_evaluate_models()
