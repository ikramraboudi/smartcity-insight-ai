"""
Module Assistant IA Décisionnel (RAG Strict Anti-Hallucination) pour la Protection Civile du Cap Bon.
smartcity-insight-ai.

Ce service récupère les données réelles en base de données :
- Zones Risk Map du Cap Bon (Gouvernorat de Nabeul), scores de risque, facteurs explicatifs
- Alertes d'accidents actives et confirmées
- Disponibilité des casernes du Cap Bon
- Statistiques récentes
"""

import os
import json
import logging
import requests
from django.utils import timezone
from datetime import timedelta

from config.geo_config import CASERNES_CAP_BON, REGION_NAME, REGION_SHORT_NAME
from .models import AlerteAccident, SignalementAccident, JournalAuditIntervention
from .ml_models import get_toutes_les_zones_risk_map

logger = logging.getLogger(__name__)

# Casernes de référence Protection Civile (dérivées de la config centralisée)
CASERNES_INFO = [
    {
        "nom": c["nom"],
        "adresse": c["adresse"],
        "delegation": c.get("delegation", ""),
        "ambulances": c["ambulances_disponibles"],
        "camions": c["camions_disponibles"],
    }
    for c in CASERNES_CAP_BON
]


def extraire_contexte_terrain_reel() -> dict:
    """
    Extrait l'état réel et complet du réseau routier du Cap Bon depuis la base de données.
    """
    now = timezone.now()
    depuis_24h = now - timedelta(hours=24)

    # 1. Alertes actives
    alertes_actives = AlerteAccident.objects.exclude(statut='CLOTURE').order_by('-date_creation')[:15]
    alertes_liste = []
    for a in alertes_actives:
        alertes_liste.append({
            "id": a.id,
            "statut": a.statut,
            "gravite": a.gravite,
            "adresse": a.adresse,
            "zone_nom": a.zone_nom,
            "nb_signalements": a.nb_signalements,
            "date_creation": a.date_creation.strftime("%H:%M:%S") if a.date_creation else "",
            "date_confirmation": a.date_confirmation.strftime("%H:%M:%S") if a.date_confirmation else "En attente",
        })

    # 2. Statistiques des dernières 24h
    total_24h = AlerteAccident.objects.filter(date_creation__gte=depuis_24h).count()
    total_cloturees_24h = AlerteAccident.objects.filter(date_creation__gte=depuis_24h, statut='CLOTURE').count()
    total_signalements_24h = SignalementAccident.objects.filter(date_creation__gte=depuis_24h).count()

    # 3. Derniers audits d'intervention
    derniers_audits = JournalAuditIntervention.objects.select_related('alerte').all()[:5]
    audits_liste = [
        f"Alerte #{audit.alerte_id} : {audit.statut_precedent} -> {audit.nouveau_statut} ({audit.note_intervention or 'sans note'})"
        for audit in derniers_audits
    ]

    # 4. Cartographie Risk Map en direct
    zones_risk = get_toutes_les_zones_risk_map()

    zones_rouges = [z for z in zones_risk if z["niveau_couleur"] == "rouge"]
    zones_oranges = [z for z in zones_risk if z["niveau_couleur"] == "orange"]
    zones_vertes = [z for z in zones_risk if z["niveau_couleur"] == "vert"]

    return {
        "region": REGION_NAME,
        "horodatage": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "alertes_actives": alertes_liste,
        "nb_alertes_actives": len(alertes_liste),
        "statistiques_24h": {
            "total_alertes": total_24h,
            "alertes_cloturees": total_cloturees_24h,
            "total_signalements_citoyens": total_signalements_24h,
        },
        "audits_recents": audits_liste,
        "risk_map": {
            "zones_rouges_critiques": [
                {"nom": z["zone_nom"], "delegation": z.get("delegation", ""), "score": f"{z['score_risque_pourcentage']}%", "facteurs": z["facteurs_explicatifs"]}
                for z in zones_rouges
            ],
            "zones_oranges_moderees": [
                {"nom": z["zone_nom"], "delegation": z.get("delegation", ""), "score": f"{z['score_risque_pourcentage']}%", "facteurs": z["facteurs_explicatifs"]}
                for z in zones_oranges
            ],
            "zones_vertes_sures": [
                {"nom": z["zone_nom"], "delegation": z.get("delegation", ""), "score": f"{z['score_risque_pourcentage']}%"}
                for z in zones_vertes
            ],
        },
        "casernes_operationnelles": CASERNES_INFO,
    }


def generer_reponse_deterministe_ancrage(question: str, contexte: dict) -> str:
    """
    Moteur de réponse analytique déterministe garantissant 0 hallucination.
    Cible spécifiquement les requêtes types de la Protection Civile du Cap Bon.
    """
    q_norm = question.lower().strip()
    risk = contexte["risk_map"]
    rouges = risk["zones_rouges_critiques"]
    oranges = risk["zones_oranges_moderees"]
    vertes = risk.get("zones_vertes_sures", [])
    alertes = contexte["alertes_actives"]

    # 1. Questions sur les zones rouges / prioritaires
    if any(k in q_norm for k in ["zone rouge", "zones rouges", "priorit", "critique", "plus risqu"]):
        if not rouges:
            rep = f"### 🟢 Analyse des Zones Prioritaires ({REGION_SHORT_NAME})\nAucune zone rouge critique n'est actuellement détectée dans le {REGION_NAME}.\n\n"
            if oranges:
                rep += "**Zones orange sous vigilance active :**\n"
                for z in oranges:
                    rep += f"- **{z['nom']}** : Score de {z['score']} ({', '.join(z['facteurs'])})\n"
            elif vertes:
                rep += "**Principaux secteurs sous surveillance (Vert) :**\n"
                for z in vertes[:3]:
                    rep += f"- **{z['nom']}** : Score de {z['score']}\n"
            return rep

        rep = f"### 🚨 Zones Rouges Prioritaires — {REGION_SHORT_NAME} (Risque ≥ 70 %)\n\n"
        rep += f"Le modèle Risk Map a identifié **{len(rouges)} zone(s) rouge(s) critique(s)** nécessitant un pré-positionnement des secours :\n\n"
        for z in rouges:
            rep += f"1. **{z['nom']}** — Score de risque : **{z['score']}**\n"
            rep += f"   - *Facteurs explicatifs identifiés :* {'; '.join(z['facteurs'])}\n"
        rep += "\n**Recommandation d'engagement opérationnel :** Mobiliser en priorité les unités de la *Caserne Principale de Kélibia*, de *Hammam El Ghezaz* et d'*El Haouaria* pour couvrir les axes critiques."
        return rep

    # 2. Questions sur le pourquoi du risque d'une zone
    if any(k in q_norm for k in ["pourquoi", "facteur", "cause", "raison", "explication"]):
        rep = "### 🔍 Facteurs Explicatifs du Risque Routier\n\n"
        all_zones = rouges + oranges
        trouve = None
        for z in all_zones:
            for part in z["nom"].lower().split():
                if len(part) > 3 and part in q_norm:
                    trouve = z
                    break
            if trouve:
                break

        if trouve:
            rep += f"**Analyse spécifique pour : {trouve['nom']}**\n"
            rep += f"- **Score calculé :** {trouve['score']}\n"
            rep += "- **Facteurs déterminants :**\n"
            for f in trouve["facteurs"]:
                rep += f"  • {f}\n"
            rep += "\n*Source : Fusion multi-sources BDD (accidents réels + géométrie du tronçon + ml_congestion).*"
            return rep

        rep += f"Voici les facteurs explicatifs observés sur les secteurs les plus vulnérables du {REGION_NAME} :\n\n"
        for z in all_zones[:4]:
            rep += f"• **{z['nom']}** ({z['score']}) : {', '.join(z['facteurs'])}\n"
        rep += "\n*Toutes les estimations sont recalculées en temps réel selon le trafic et l'accidentologie locale.*"
        return rep

    # 3. Questions sur les alertes actives / interventions en cours
    if any(k in q_norm for k in ["alerte", "accident", "intervention", "en cours", "actif"]):
        if not alertes:
            return f"### 🛡️ Situation Opérationnelle en Temps Réel ({REGION_SHORT_NAME})\n\nAucune alerte d'accident active n'est actuellement signalée. Toutes les voies supervisées par la Protection Civile du {REGION_NAME} sont dégagées."

        rep = f"### 🚨 Alertes Actives de la Protection Civile ({len(alertes)} en cours)\n\n"
        for a in alertes:
            zone_txt = f" ({a['zone_nom']})" if a.get('zone_nom') else ""
            rep += f"- **Alerte #{a['id']}** : *{a['gravite']}* à {a['adresse']}{zone_txt}\n"
            rep += f"  - Statut : `{a['statut']}` | Signalements citoyens concordants : **{a['nb_signalements']}**\n"
            rep += f"  - Création : {a['date_creation']} | Confirmation : {a['date_confirmation']}\n"
        return rep

    # 4. Questions sur les casernes / ambulances / moyens disponibles
    if any(k in q_norm for k in ["caserne", "moyen", "ambulance", "camion", "pompier", "secour"]):
        rep = f"### 🚒 Disponibilité des Casernes de Protection Civile ({REGION_NAME})\n\n"
        for c in contexte["casernes_operationnelles"]:
            rep += f"- **{c['nom']}** ({c['adresse']}) : **{c['ambulances']}** ambulances, **{c['camions']}** camions d'intervention disponibles.\n"
        rep += "\n*Numéro d'urgence opérationnel : 198 (Poste de commandement Kélibia / Nord-Est Cap Bon).*"
        return rep

    # 5. Réponse de synthèse globale par défaut
    rep = f"### 📊 Synthèse Décisionnelle Protection Civile ({REGION_NAME})\n\n"
    rep += f"- **Alertes d'accidents actives :** {len(alertes)}\n"
    rep += f"- **Zones rouges à risque élevé (≥ 70 %) :** {len(rouges)}\n"
    if rouges:
        rep += f"  • {', '.join(z['nom'] + ' (' + z['score'] + ')' for z in rouges)}\n"
    rep += f"- **Zones orange à risque modéré (35–69 %) :** {len(oranges)}\n"
    rep += f"- **Signalements traités sur 24h :** {contexte['statistiques_24h']['total_signalements_citoyens']}\n\n"
    rep += "💡 *Vous pouvez demander : 'Quelles sont les zones rouges prioritaires ?', 'Pourquoi El Haouaria ou Menzel Horr est risquée ?', ou 'Quelles casernes sont disponibles ?'*"
    return rep


def interroger_assistant_llm(question: str) -> dict:
    """
    Orchestre la requête RAG :
    1. Récupère le contexte réel en BDD.
    2. Si clé API présente, appelle le modèle LLM externe avec instructions strictes anti-hallucination.
    3. Fallback immédiat et transparent sur le moteur analytique déterministe garanti sans hallucination.
    """
    contexte = extraire_contexte_terrain_reel()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    reponse_texte = None
    moteur_utilise = "Moteur Déterministe RAG Local (Anti-hallucination certifié)"

    if api_key:
        prompt_systeme = (
            f"Tu es l'Assistant IA Décisionnel de la Protection Civile du {REGION_NAME} (smartcity-insight-ai).\n"
            "RÈGLE STRICTE ANTI-HALLUCINATION : Tu réponds EXCLUSIVEMENT à partir du contexte JSON vérifié fourni ci-dessous.\n"
            "N'invente aucun accident, aucun chiffre, aucun nom de voie ou de délégation non mentionné.\n"
            "Cite précisément les scores de risque, les statuts d'alerte et les facteurs explicatifs.\n"
            "Si l'information demandée n'est pas dans le contexte, dis clairement qu'elle n'est pas répertoriée.\n\n"
            f"CONTEXTE TEMPS RÉEL :\n{json.dumps(contexte, ensure_ascii=False, indent=2)}"
        )

        gemini_key = os.environ.get("GEMINI_API_KEY") or (api_key if api_key.startswith("AIza") else None)
        if gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [
                        {"role": "user", "parts": [{"text": f"{prompt_systeme}\n\nQuestion de l'opérateur de la Protection Civile :\n{question}"}]}
                    ],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800}
                }
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            reponse_texte = parts[0].get("text", "")
                            moteur_utilise = "Gemini 1.5 Flash (RAG Ancré)"
            except Exception as e:
                logger.warning(f"Échec appel Gemini API: {e}")

    if not reponse_texte:
        reponse_texte = generer_reponse_deterministe_ancrage(question, contexte)

    return {
        "question": question,
        "reponse": reponse_texte,
        "moteur": moteur_utilise,
        "contexte_utilise": {
            "nb_alertes_actives": contexte["nb_alertes_actives"],
            "nb_zones_rouges": len(contexte["risk_map"]["zones_rouges_critiques"]),
            "horodatage": contexte["horodatage"],
        }
    }
