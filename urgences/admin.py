from django.contrib import admin
from .models import AlerteAccident, Chantier, SignalementAccident

admin.site.register(AlerteAccident)
admin.site.register(SignalementAccident)
admin.site.register(Chantier)
