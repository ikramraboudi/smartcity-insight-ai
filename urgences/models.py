from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class SignalementAccident(models.Model):
    GRAVITE_CHOICES = [
        ('FAIBLE', 'Faible'),
        ('MOYENNE', 'Moyenne'),
        ('GRAVE', 'Grave / Critique'),
    ]

    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    adresse = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    gravite_estimee = models.CharField(max_length=20, choices=GRAVITE_CHOICES, default='MOYENNE')
    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Signalement ({self.latitude}, {self.longitude}) - {self.gravite_estimee}"


class AlerteAccident(models.Model):
    STATUT_CHOICES = [
        ('A_CONFIRMER', 'À confirmer'),
        ('CONFIRME', 'Confirmé (Reçue)'),
        ('PRISE_EN_CHARGE', 'Prise en charge'),
        ('EN_INTERVENTION', 'En cours (En intervention)'),
        ('CLOTURE', 'Clôturée'),
    ]

    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    adresse = models.CharField(max_length=255, blank=True)
    zone_nom = models.CharField(max_length=120, blank=True, default='')
    gravite = models.CharField(max_length=20, default='MOYENNE')
    statut = models.CharField(max_length=25, choices=STATUT_CHOICES, default='A_CONFIRMER', db_index=True)
    nb_signalements = models.PositiveIntegerField(default=1)
    signalements_lies = models.ManyToManyField(SignalementAccident, related_name='alertes')

    # Horodatage strict de chaque étape (exigé pour la Protection Civile)
    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)
    date_prise_en_charge = models.DateTimeField(null=True, blank=True)
    date_en_intervention = models.DateTimeField(null=True, blank=True)
    date_cloture = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Alerte #{self.id} - {self.statut} ({self.nb_signalements} sig.)"


class JournalAudit(models.Model):
    """Journal d'audit général pour la compatibilité."""
    alerte = models.ForeignKey(AlerteAccident, on_delete=models.CASCADE, related_name='audits')
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    horodatage = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.horodatage}] Alerte #{self.alerte.id} : {self.action}"


class JournalAuditIntervention(models.Model):
    """
    Journal d'audit strict exigé pour le suivi des interventions de la Protection Civile :
    Enregistre chaque changement d'état avec l'alerte, l'intervenant, les statuts avant/après,
    l'horodatage exact et la note d'intervention.
    """
    alerte = models.ForeignKey(AlerteAccident, on_delete=models.CASCADE, related_name='audits_intervention')
    intervenant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    matricule_intervenant = models.CharField(max_length=64, blank=True, default='')
    statut_precedent = models.CharField(max_length=50)
    nouveau_statut = models.CharField(max_length=50)
    horodatage = models.DateTimeField(auto_now_add=True)
    note_intervention = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-horodatage']
        verbose_name = "Audit d'intervention"
        verbose_name_plural = "Audits d'interventions"

    def __str__(self):
        return f"[{self.horodatage}] Alerte #{self.alerte_id}: {self.statut_precedent} -> {self.nouveau_statut}"
