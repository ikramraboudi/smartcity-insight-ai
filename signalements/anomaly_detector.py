"""
Module ML — Détection d'Anomalies Spatio-Temporelles (Priorité 3).
Utilise sklearn.ensemble.IsolationForest (algorithme non supervisé) pour identifier
les sursauts anormaux de signalements dans une zone donnée (ex: nid-de-poule massif,
panne d'éclairage sectorielle, dégradation brutale) tout en appliquant des garde-fous
stricts contre les faux positifs.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from django.utils import timezone
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.geo_config import DEFAULT_COORDS, SPATIAL_CONFIG
from urgences.services import distance_metres
from .models import AlerteAnomalie, Signalement

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    'nb_signalements',
    'ratio_gravite_elevee',
    'concentration_spatiale',
    'densite_horaire',
    'ecart_baseline',
]

MIN_REPORTS_FOR_ANOMALY = 3
DEFAULT_WINDOW_HOURS = 6

_cached_pipeline: Optional[Pipeline] = None


def _build_reference_baseline_dataframe() -> pd.DataFrame:
    """
    Génère un socle de référence calibré représentant l'activité normale
    d'une délégation du Cap Bon sur des fenêtres de 6 heures (1 à 2 signalements
    espacés de gravité modérée), afin d'éviter les faux positifs à froid lorsque
    l'historique en base de données est encore restreint.
    """
    rng = np.random.default_rng(42)
    n_normal = 160

    nb_sig = rng.choice([1, 2, 3], size=n_normal, p=[0.62, 0.30, 0.08]).astype(float)
    ratio_grav = np.where(
        nb_sig <= 2,
        rng.uniform(0.0, 0.5, size=n_normal),
        rng.uniform(0.0, 0.34, size=n_normal),
    )
    concentration = rng.uniform(0.15, 0.62, size=n_normal)
    densite_h = nb_sig / float(DEFAULT_WINDOW_HOURS)
    ecart_base = nb_sig / rng.uniform(0.8, 1.5, size=n_normal)

    return pd.DataFrame({
        'nb_signalements': nb_sig,
        'ratio_gravite_elevee': ratio_grav,
        'concentration_spatiale': concentration,
        'densite_horaire': densite_h,
        'ecart_baseline': ecart_base,
    })


def _extract_historical_windows_df(fenetre_heures: int = DEFAULT_WINDOW_HOURS) -> pd.DataFrame:
    """
    Construit des vecteurs de caractéristiques sur les tranches historiques (> fenetre_heures)
    des 30 derniers jours en base pour enrichir la distribution de référence.
    """
    now = timezone.now()
    cutoff_recent = now - timedelta(hours=fenetre_heures)
    cutoff_hist = now - timedelta(days=30)

    qs = (
        Signalement.objects.filter(
            date_creation__gte=cutoff_hist,
            date_creation__lt=cutoff_recent,
        )
        .exclude(statut=Signalement.Statut.REJETE_SPAM)
        .values('quartier', 'categorie', 'gravite', 'latitude', 'longitude', 'date_creation')
    )

    buckets: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}
    for row in qs:
        epoch_bucket = int(row['date_creation'].timestamp() // (fenetre_heures * 3600))
        key = (row['quartier'], row['categorie'], epoch_bucket)
        buckets.setdefault(key, []).append(row)

    rows = []
    for _, items in buckets.items():
        feat = _compute_window_features(items, baseline_avg=1.2, fenetre_heures=fenetre_heures)
        rows.append(feat['features'])

    if not rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS)
    return pd.DataFrame(rows)[FEATURE_COLUMNS]


def get_isolation_forest_pipeline(force_refit: bool = False) -> Pipeline:
    """
    Entraîne (ou retourne depuis le cache mémoire) le pipeline StandardScaler + IsolationForest.
    """
    global _cached_pipeline
    if _cached_pipeline is not None and not force_refit:
        return _cached_pipeline

    ref_df = _build_reference_baseline_dataframe()
    try:
        hist_df = _extract_historical_windows_df(DEFAULT_WINDOW_HOURS)
        if len(hist_df) > 0:
            train_df = pd.concat([ref_df, hist_df], ignore_index=True)
        else:
            train_df = ref_df
    except Exception:
        train_df = ref_df

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('iforest', IsolationForest(
            n_estimators=100,
            contamination=0.04,
            max_samples='auto',
            random_state=42,
        )),
    ])
    pipeline.fit(train_df[FEATURE_COLUMNS])
    _cached_pipeline = pipeline
    return _cached_pipeline


def _compute_baseline_average(quartier: str, categorie: str, fenetre_heures: int) -> float:
    """Estime la moyenne historique par tranche de `fenetre_heures` sur 30 jours."""
    now = timezone.now()
    cutoff_recent = now - timedelta(hours=fenetre_heures)
    cutoff_hist = now - timedelta(days=30)

    hist_count = (
        Signalement.objects.filter(
            quartier=quartier,
            categorie=categorie,
            date_creation__gte=cutoff_hist,
            date_creation__lt=cutoff_recent,
        )
        .exclude(statut=Signalement.Statut.REJETE_SPAM)
        .count()
    )
    nb_windows = max(1.0, (30.0 * 24.0) / float(fenetre_heures))
    return max(0.75, hist_count / nb_windows)


def _compute_window_features(
    items: List[Dict[str, Any]],
    baseline_avg: float,
    fenetre_heures: int,
) -> Dict[str, Any]:
    """Calcule le centroïde GPS et le vecteur de variables pour Isolation Forest."""
    count = len(items)
    if count == 0:
        return {
            'lat_centre': DEFAULT_COORDS['latitude'],
            'lng_centre': DEFAULT_COORDS['longitude'],
            'features': {c: 0.0 for c in FEATURE_COLUMNS},
        }

    lats = [float(it['latitude']) for it in items]
    lngs = [float(it['longitude']) for it in items]
    lat_centre = sum(lats) / count
    lng_centre = sum(lngs) / count

    if count > 1:
        dists = [distance_metres(lat_centre, lng_centre, it['latitude'], it['longitude']) for it in items]
        mean_disp_m = sum(dists) / count
    else:
        mean_disp_m = 500.0

    # Plus les signalements sont proches du centroïde, plus la concentration approche 1.0
    # Échelle calibrée pour les délégations multi-quartiers du Cap Bon
    spatial_scale_m = float(SPATIAL_CONFIG.get('anomaly_spatial_scale_m', 400.0))
    concentration_spatiale = 1.0 / (1.0 + (mean_disp_m / spatial_scale_m))

    high_grav_count = sum(
        1 for it in items
        if it.get('gravite') in (Signalement.Gravite.ELEVEE, Signalement.Gravite.CRITIQUE)
    )
    ratio_grav = high_grav_count / float(count)
    densite_h = count / float(max(1, fenetre_heures))
    ecart_baseline = count / max(0.5, baseline_avg)

    return {
        'lat_centre': round(lat_centre, 6),
        'lng_centre': round(lng_centre, 6),
        'mean_disp_m': round(mean_disp_m, 1),
        'high_grav_count': high_grav_count,
        'features': {
            'nb_signalements': float(count),
            'ratio_gravite_elevee': float(ratio_grav),
            'concentration_spatiale': float(concentration_spatiale),
            'densite_horaire': float(densite_h),
            'ecart_baseline': float(ecart_baseline),
        },
    }


def _format_explication(
    quartier: str,
    categorie: str,
    count: int,
    fenetre_heures: int,
    high_grav_count: int,
    mean_disp_m: float,
    score_pct: float,
) -> str:
    cat_label = dict(Signalement.Categorie.choices).get(categorie, categorie)
    parts = [
        f"Pic anormal de « {cat_label} » détecté dans le secteur {quartier} : "
        f"{count} signalement(s) sur les {fenetre_heures} dernières heures (score Isolation Forest : {score_pct:.0f} %)."
    ]
    if high_grav_count > 0:
        parts.append(f"{high_grav_count} incident(s) de gravité Élevée/Critique.")
    if mean_disp_m <= 250:
        parts.append(f"Forte concentration géographique (dispersion moyenne ~{int(mean_disp_m)} m).")
    return " ".join(parts)


def evaluer_anomalie_zone(
    quartier: str,
    categorie: str,
    fenetre_heures: int = DEFAULT_WINDOW_HOURS,
    persist: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Évalue si la paire (quartier, categorie) présente un sursaut anormal dans les
    dernières `fenetre_heures` via Isolation Forest.
    Retourne le résumé de l'anomalie (ou None si comportement normal).
    """
    now = timezone.now()
    fenetre_debut = now - timedelta(hours=fenetre_heures)

    items = list(
        Signalement.objects.filter(
            quartier=quartier,
            categorie=categorie,
            date_creation__gte=fenetre_debut,
        )
        .exclude(statut=Signalement.Statut.REJETE_SPAM)
        .values('id', 'gravite', 'latitude', 'longitude', 'date_creation')
    )

    count = len(items)
    # Garde-fou anti-faux positif #1 : un incident isolé (< 3) ne déclenche jamais d'anomalie
    if count < MIN_REPORTS_FOR_ANOMALY:
        return None

    baseline_avg = _compute_baseline_average(quartier, categorie, fenetre_heures)
    computed = _compute_window_features(items, baseline_avg=baseline_avg, fenetre_heures=fenetre_heures)
    feat = computed['features']

    pipeline = get_isolation_forest_pipeline()
    df_sample = pd.DataFrame([feat])[FEATURE_COLUMNS]

    pred = int(pipeline.predict(df_sample)[0])  # -1 = anomalie, 1 = normal
    decision_raw = float(pipeline.decision_function(df_sample)[0])
    # Normalisation intuitive (0..100%) : decision_raw < 0 -> > 50%
    score_pct = round(float(np.clip(50.0 + (-decision_raw) * 180.0, 0.0, 100.0)), 1)

    if pred != -1:
        return None

    # Garde-fou anti-faux positif #2 : à la frontière (count == 3), exiger un signal fort
    # (gravité élevée, concentration < 250 m ou score >= 58 %)
    if count == MIN_REPORTS_FOR_ANOMALY:
        if (
            feat['ratio_gravite_elevee'] < 0.34
            and feat['concentration_spatiale'] < 0.55
            and score_pct < 58.0
        ):
            return None

    if score_pct >= 78.0 or count >= 6 or feat['ratio_gravite_elevee'] >= 0.7:
        severite = AlerteAnomalie.Severite.CRITIQUE
    elif score_pct >= 62.0 or count >= 4:
        severite = AlerteAnomalie.Severite.ELEVEE
    else:
        severite = AlerteAnomalie.Severite.MODERE

    explication = _format_explication(
        quartier=quartier,
        categorie=categorie,
        count=count,
        fenetre_heures=fenetre_heures,
        high_grav_count=computed['high_grav_count'],
        mean_disp_m=computed['mean_disp_m'],
        score_pct=score_pct,
    )

    alerte_obj = None
    if persist:
        # Déduplication : mise à jour de l'alerte ACTIVE existante sur la fenêtre active
        alerte_existante = (
            AlerteAnomalie.objects.filter(
                quartier=quartier,
                categorie=categorie,
                statut=AlerteAnomalie.Statut.ACTIVE,
                date_detection__gte=fenetre_debut,
            )
            .order_by('-date_detection')
            .first()
        )
        if alerte_existante:
            alerte_existante.severite = severite
            alerte_existante.score_anomalie = score_pct
            alerte_existante.decision_raw = round(decision_raw, 4)
            alerte_existante.nb_signalements = count
            alerte_existante.latitude_centre = computed['lat_centre']
            alerte_existante.longitude_centre = computed['lng_centre']
            alerte_existante.explication = explication
            alerte_existante.save()
            alerte_obj = alerte_existante
        else:
            alerte_obj = AlerteAnomalie.objects.create(
                quartier=quartier,
                categorie=categorie,
                severite=severite,
                score_anomalie=score_pct,
                decision_raw=round(decision_raw, 4),
                nb_signalements=count,
                fenetre_heures=fenetre_heures,
                latitude_centre=computed['lat_centre'],
                longitude_centre=computed['lng_centre'],
                explication=explication,
            )

    return {
        'id': alerte_obj.id if alerte_obj else None,
        'quartier': quartier,
        'categorie': categorie,
        'severite': severite,
        'score_anomalie': score_pct,
        'decision_raw': round(decision_raw, 4),
        'nb_signalements': count,
        'fenetre_heures': fenetre_heures,
        'latitude_centre': computed['lat_centre'],
        'longitude_centre': computed['lng_centre'],
        'explication': explication,
    }


def scanner_toutes_anomalies(fenetre_heures: int = DEFAULT_WINDOW_HOURS) -> List[Dict[str, Any]]:
    """
    Analyse toutes les paires (quartier, categorie) actives sur les dernières `fenetre_heures`.
    """
    fenetre_debut = timezone.now() - timedelta(hours=fenetre_heures)
    paires = (
        Signalement.objects.filter(date_creation__gte=fenetre_debut)
        .exclude(statut=Signalement.Statut.REJETE_SPAM)
        .values_list('quartier', 'categorie')
        .distinct()
    )
    detectees = []
    for quartier, categorie in paires:
        res = evaluer_anomalie_zone(quartier, categorie, fenetre_heures=fenetre_heures, persist=True)
        if res is not None:
            detectees.append(res)
    return detectees


def detect_anomalies_6h() -> List[Dict[str, Any]]:
    """
    Exécute le pipeline Isolation Forest sur la fenêtre active standard de 6 heures.
    """
    return scanner_toutes_anomalies(fenetre_heures=DEFAULT_WINDOW_HOURS)
