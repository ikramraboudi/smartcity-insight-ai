"""
Générateur et fusionneur de données historiques pour le Module D (Prédiction de Congestion — Cap Bon).
Conformes aux sections 8.1, 8.2 et 8.4 :
- Source A : historique des travaux, incidents et signalements
- Source B : géométrie et caractéristiques des 12 corridors routiers du Cap Bon
- Source C : calendrier, créneaux horaires, météo et type de route
"""

import pandas as pd
from .data_pipeline import CAP_BON_STREETS, build_chronological_dataset, get_creneau_horaire

STREETS_SPEC = CAP_BON_STREETS
determine_creneau_horaire = get_creneau_horaire


def generate_historical_dataset(
    start_date: str = "2026-08-01",
    days: int = 90,
    output_path: str = "ml_congestion/data/traffic_historical_dataset.csv",
) -> pd.DataFrame:
    """Délègue la génération chronologique vers le pipeline Cap Bon unifié."""
    return build_chronological_dataset(start_date=start_date, days=days, csv_path=output_path)


if __name__ == "__main__":
    generate_historical_dataset()
