"""
Commande Django de Simulation pour la Soutenance & Démonstration Live (Étudiant 3).
Usage :
  python manage.py simulate_urgences --mode fausse_alerte
  python manage.py simulate_urgences --mode accident_confirme
  python manage.py simulate_urgences --mode risk_map
  python manage.py simulate_urgences --mode all
"""

from django.core.management.base import BaseCommand
from urgences.simulation import (
    executer_simulation_fausse_alerte,
    executer_simulation_accident_confirme,
    executer_simulation_risk_map_cap_bon,
)


class Command(BaseCommand):
    help = "Exécute les simulations de la Protection Civile (Anti-Fausse Alerte, Clustering < 5s, Risk Map Cap Bon)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            default='all',
            choices=['fausse_alerte', 'accident_confirme', 'risk_map', 'all'],
            help="Type de scénario à exécuter (fausse_alerte | accident_confirme | risk_map | all)"
        )

    def handle(self, *args, **options):
        mode = options['mode']
        self.stdout.write(self.style.NOTICE(f"⚡ Lancement de la simulation urgences (mode: {mode})..."))

        if mode in ('fausse_alerte', 'all'):
            self.stdout.write("\n--- [1] Simulation Anti-Fausse Alerte (Signalement Isolé) ---")
            res_fausse = executer_simulation_fausse_alerte()
            self.stdout.write(f"• Alerte #{res_fausse['alerte_id']} créée avec statut : {res_fausse['statut_alerte']}")
            self.stdout.write(f"• Confirmation pompiers : {res_fausse['alerte_confirmee_pompiers']} (Pas d'alarme)")
            self.stdout.write(self.style.SUCCESS(f"✔ {res_fausse['message']}"))

        if mode in ('accident_confirme', 'all'):
            self.stdout.write("\n--- [2] Simulation Accident Confirmé (Clustering PostGIS < 5s) ---")
            res_confirme = executer_simulation_accident_confirme()
            self.stdout.write(f"• Alerte #{res_confirme['alerte_id']} : {res_confirme['nb_signalements_fusionnes']} signalements fusionnés")
            self.stdout.write(f"• Statut : {res_confirme['statut_alerte']} (Confirmé)")
            self.stdout.write(f"• Diffusion temps réel : {res_confirme['diffusion_temps_reel']}")
            self.stdout.write(self.style.SUCCESS(f"✔ {res_confirme['message']}"))

        if mode in ('risk_map', 'all'):
            self.stdout.write("\n--- [3] Simulation Risk Map Cap Bon (Historiques & Prédictions) ---")
            res_risk = executer_simulation_risk_map_cap_bon()
            self.stdout.write(f"• Secteurs analysés : {res_risk['nb_secteurs_evalues']}")
            self.stdout.write(f"• Répartition : {res_risk['repartition']['rouges']} Rouges, {res_risk['repartition']['oranges']} Oranges, {res_risk['repartition']['vertes']} Vertes")
            self.stdout.write(self.style.SUCCESS(f"✔ {res_risk['message']}"))

        self.stdout.write(self.style.SUCCESS("\n🎉 Simulation terminée avec succès !"))
