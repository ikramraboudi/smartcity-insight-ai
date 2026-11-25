import logging
import threading
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Signalement
from urgences.models import SignalementAccident, AlerteAccident, JournalAudit
from urgences.services import traiter_signalement, diffuser_alerte_temps_reel

logger = logging.getLogger(__name__)

# Gestionnaire de récursion pour éviter les boucles infinies de synchronisation
_sync_state = threading.local()


def _is_syncing() -> bool:
    return getattr(_sync_state, 'active', False)


class _SyncContext:
    def __enter__(self):
        _sync_state.active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _sync_state.active = False


# ==============================================================================
# 1. PASSERELLE CITOYEN ➔ PROTECTION CIVILE (Création automatique d'alerte)
# ==============================================================================
@receiver(post_save, sender=Signalement)
def synchroniser_signalement_vers_protection_civile(sender, instance: Signalement, created: bool, **kwargs):
    """
    Écoute la création et la modification d'un Signalement citoyen :
    1. À la création : si le signalement est de catégorie ACCIDENT ou de gravité ELEVEE/CRITIQUE,
       crée immédiatement l'alerte d'urgence et la diffuse par WebSocket (< 5s) aux pompiers.
    2. À la mise à jour (Municipal ➔ Protection Civile) : répercute les changements de statut
       (EN_COURS ➔ PRISE_EN_CHARGE, RESOLU ➔ CLOTURE) sur l'alerte d'urgence liée.
    """
    if _is_syncing():
        return

    # --------------------------------------------------------------------------
    # Cas 1 : Création d'un nouveau signalement nécessitant les secours d'urgence
    # --------------------------------------------------------------------------
    if created:
        if instance.statut == Signalement.Statut.REJETE_SPAM:
            return

        est_urgence = (
            instance.categorie == Signalement.Categorie.ACCIDENT
            or instance.gravite in (Signalement.Gravite.CRITIQUE, Signalement.Gravite.ELEVEE)
        )

        if est_urgence and not instance.alerte_liee:
            try:
                # Mapping de la gravité municipale vers la gravité d'intervention Protection Civile
                gravite_urgence = 'GRAVE' if instance.gravite in (
                    Signalement.Gravite.CRITIQUE,
                    Signalement.Gravite.ELEVEE,
                ) else ('MOYENNE' if instance.gravite == Signalement.Gravite.MOYENNE else 'FAIBLE')

                adresse_clean = (
                    instance.adresse_texte
                    or (f"{instance.quartier}, Tunis" if instance.quartier else "Tunis")
                )
                desc_clean = instance.description or f"Signalement {instance.get_categorie_display()} ({instance.get_gravite_display()})"

                # Création du signalement accident sous-jacent
                sig_accident = SignalementAccident.objects.create(
                    latitude=instance.latitude,
                    longitude=instance.longitude,
                    adresse=adresse_clean,
                    description=desc_clean,
                    gravite_estimee=gravite_urgence,
                )

                # Regroupement spatial PostGIS et confirmation immédiate
                alerte = traiter_signalement(sig_accident, valide_par_agent=True)

                # Liaison de l'alerte au signalement municipal (mise à jour directe sans ré-émettre post_save)
                Signalement.objects.filter(pk=instance.pk).update(alerte_liee=alerte)
                instance.alerte_liee = alerte

                # Enregistrement au journal d'audit de la Protection Civile
                JournalAudit.objects.create(
                    alerte=alerte,
                    action=f"Alerte déclenchée automatiquement par Signalement Citoyen #{instance.id} ({instance.categorie})"
                )

                # Diffusion en temps réel garantie via Django Channels WebSocket (< 5s)
                try:
                    diffuser_alerte_temps_reel(alerte)
                except Exception as ws_err:
                    logger.warning(f"Diffusion WebSocket temps réel non bloquante : {ws_err}")

                logger.info(
                    f"[SYNCHRO] Signalement {instance.id} lié à l'Alerte #{alerte.id} et diffusé à la Protection Civile."
                )

            except Exception as e:
                logger.error(f"[SYNCHRO ERROR] Échec création alerte pour signalement {instance.id}: {e}", exc_info=True)

        # Analyse ML non supervisée (Isolation Forest) pour détecter un pic anormal sur la zone
        try:
            from .anomaly_detector import evaluer_anomalie_zone
            anomalie = evaluer_anomalie_zone(
                quartier=instance.quartier,
                categorie=instance.categorie,
                persist=True,
            )
            if anomalie:
                logger.info(
                    f"[ANOMALIE IA] Sursaut détecté ({anomalie['score_anomalie']}%) : "
                    f"{anomalie['categorie']} @ {anomalie['quartier']}"
                )
        except Exception as ml_err:
            logger.warning(f"[ANOMALIE IA] Détection non bloquante ignorée : {ml_err}")

    # --------------------------------------------------------------------------
    # Cas 2 : Modification du statut municipal (Municipal ➔ Protection Civile)
    # --------------------------------------------------------------------------
    elif instance.alerte_liee:
        alerte = instance.alerte_liee
        now = timezone.now()

        with _SyncContext():
            # Municipal EN_COURS ➔ Pompier PRISE_EN_CHARGE
            if instance.statut == Signalement.Statut.EN_COURS:
                if alerte.statut not in ('PRISE_EN_CHARGE', 'EN_INTERVENTION', 'CLOTURE'):
                    alerte.statut = 'PRISE_EN_CHARGE'
                    alerte.date_prise_en_charge = now
                    alerte.save()
                    JournalAudit.objects.create(
                        alerte=alerte,
                        action="Statut 'PRISE_EN_CHARGE' répercuté depuis le Dashboard Municipal"
                    )
                    try:
                        diffuser_alerte_temps_reel(alerte)
                    except Exception as ws_err:
                        logger.warning(f"Diffusion WebSocket alerte: {ws_err}")

            # Municipal RESOLU ➔ Pompier CLOTURE
            elif instance.statut == Signalement.Statut.RESOLU:
                if alerte.statut != 'CLOTURE':
                    alerte.statut = 'CLOTURE'
                    alerte.date_cloture = now
                    alerte.save()
                    JournalAudit.objects.create(
                        alerte=alerte,
                        action="Statut 'CLOTURE' répercuté depuis le Dashboard Municipal"
                    )
                    try:
                        diffuser_alerte_temps_reel(alerte)
                    except Exception as ws_err:
                        logger.warning(f"Diffusion WebSocket alerte: {ws_err}")


# ==============================================================================
# 2. SYNCHRONISATION PROTECTION CIVILE ➔ MUNICIPAL (Statuts d'Intervention)
# ==============================================================================
@receiver(post_save, sender=AlerteAccident)
def synchroniser_protection_civile_vers_municipal(sender, instance: AlerteAccident, created: bool, **kwargs):
    """
    Écoute l'évolution de statut d'une AlerteAccident par la Protection Civile :
    - PRISE_EN_CHARGE ou EN_INTERVENTION ➔ Le signalement municipal passe à EN_COURS.
    - CLOTURE ➔ Le signalement municipal passe à RESOLU.
    """
    if _is_syncing() or created:
        return

    with _SyncContext():
        now = timezone.now()

        if instance.statut in ('PRISE_EN_CHARGE', 'EN_INTERVENTION'):
            # Met à jour tous les signalements municipaux associés non encore en cours ou résolus
            signalements_a_maj = instance.signalements_municipaux.exclude(
                statut__in=[Signalement.Statut.EN_COURS, Signalement.Statut.RESOLU]
            )
            for sig in signalements_a_maj:
                sig.statut = Signalement.Statut.EN_COURS
                sig.save(update_fields=['statut', 'date_mise_a_jour'])
                logger.info(
                    f"[SYNCHRO] Signalement {sig.id} synchronisé vers EN_COURS suite intervention Alerte #{instance.id}"
                )

        elif instance.statut == 'CLOTURE':
            # Clôture tous les signalements municipaux associés
            signalements_a_cloturer = instance.signalements_municipaux.exclude(
                statut=Signalement.Statut.RESOLU
            )
            for sig in signalements_a_cloturer:
                sig.statut = Signalement.Statut.RESOLU
                sig.save(update_fields=['statut', 'date_mise_a_jour'])
                logger.info(
                    f"[SYNCHRO] Signalement {sig.id} synchronisé vers RESOLU suite clôture Alerte #{instance.id}"
                )
