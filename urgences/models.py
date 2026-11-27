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


class Chantier(models.Model):
    """
    Chantier de voirie déclaré par le Responsable Municipal sur une rue/artère,
    affiché sur la carte opérationnelle de la Protection Civile.
    """
    PRIORITE_CHOICES = [
        ('FAIBLE', 'Faible'),
        ('MOYENNE', 'Moyenne'),
        ('ELEVEE', 'Élevée'),
        ('CRITIQUE', 'Critique'),
    ]
    STATUT_CHOICES = [
        ('PLANIFIE', 'Planifié'),
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
    ]

    titre = models.CharField(max_length=160)
    rue_nom = models.CharField(max_length=200)
    street_id = models.CharField(max_length=80, blank=True, default='')
    description = models.TextField(blank=True, default='')
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    priorite = models.CharField(max_length=20, choices=PRIORITE_CHOICES, default='MOYENNE')
    voies_bloquees = models.PositiveIntegerField(default=1)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_COURS', db_index=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    declare_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='chantiers_declares')
    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Chantier'
        verbose_name_plural = 'Chantiers'

    def __str__(self):
        return f"🚧 {self.titre} — {self.rue_nom} ({self.statut})"


class TronconRoutier(models.Model):
    """
    Corridor / tronçon routier du Nord-Est Cap Bon stocké en base spatiale PostGIS
    (table `troncon_routier` avec colonne `geom geometry(LineString, 4326)` et index GIST).
    """
    street_id = models.CharField(max_length=80, unique=True, db_index=True)
    street_name = models.CharField(max_length=200)
    zone = models.CharField(max_length=60, db_index=True)
    road_type = models.CharField(max_length=50, default='ARTERE_PRINCIPALE')
    base_speed_kmh = models.FloatField(default=50.0)
    length_km = models.FloatField(default=3.0)
    proximity_sensitive = models.BooleanField(default=False)
    alternatives = models.JSONField(default=list, blank=True)
    coordinates = models.JSONField(default=list, blank=True)
    geom_wkt = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'troncon_routier'
        ordering = ['street_id']
        verbose_name = 'Tronçon Routier (PostGIS)'
        verbose_name_plural = 'Tronçons Routiers (PostGIS)'

    def __str__(self):
        return f"{self.street_name} ({self.zone})"
