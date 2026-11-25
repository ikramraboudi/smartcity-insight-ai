# SmartCity Insight AI — Plateforme Nord-Est du Cap Bon (Kélibia • Hammam El Ghezaz • El Haouaria) 🏙️🚨

Plateforme intelligente et distribuée de détection rapide des urgences routières (< 5s), de signalements citoyens participatifs, de maintenance de la voirie et d'aide à la décision municipale.

---

## 👥 Répartition des Rôles & Modules (Cahier des Charges)

| Acteur & Espace | Étudiant Responsable | Responsabilités Clés | Statut |
| :--- | :--- | :--- | :--- |
| **🚨 Protection Civile** (`/protection-civile`) | **Étudiant 3** | WebSockets `< 5s` (Daphne + Redis), Google Routes API + Trafic temps réel, machine d'état d'intervention, Risk Map (Random Forest) | **Opérationnel ✅** |
| **📱 Espace Citoyen** (`/citoyen`) | **Étudiant 2** | Formulaire de signalement participatif, modèle IA de floutage RGPD (visages/plaques), algorithme anti-abus | **En cours 🟡** |
| **👷 Espace Agent de Terrain** (`/agent`) | **Étudiant 1** | Modélisation des tronçons routiers PostGIS (`LineString` + index GIST), missions d'intervention voirie | **En cours 🟡** |
| **📊 Dashboard Décisionnel** (`/responsable`) | **Étudiant 2** | Requêtes d'agrégation spatiales PostGIS (`ST_Within`, arrondissements), KPIs de résolution et heatmaps | **En cours 🟡** |

---

## 🏗️ Architecture Globale & Stack Technique

```text
┌────────────────────────────────────────────────────────────────────────┐
│               Frontend React 19 + TypeScript + Vite                    │
│   (react-router-dom : Accueil Hub | Protection Civile | Citoyen | ...)  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ HTTP REST & WebSocket (ws://)
┌─────────────────────────────────▼──────────────────────────────────────┐
│                  Backend Django 6 + ASGI Daphne                        │
│          (Django REST Framework + Django Channels 4)                   │
└─────────────────┬──────────────────────────────────────┬───────────────┘
                  │                                      │
┌─────────────────▼──────────────┐     ┌─────────────────▼──────────────┐
│  PostgreSQL 16 + PostGIS 3.4   │     │            Redis 7             │
│  (Géométries & Agrégations)    │     │  (Broker Channel Layers < 5s)  │
└────────────────────────────────┘     └────────────────────────────────┘
```

---

## 🚀 Démarrage Rapide

### 1. Démarrer les Services Partagés (Docker : PostGIS + Redis)
À la racine du projet :
```powershell
docker compose up -d
```
> Cela lance automatiquement **PostgreSQL 16 avec PostGIS** sur le port `5432` et **Redis** sur le port `6379`.

### 2. Démarrer le Backend Django Channels (ASGI Daphne)
Dans un terminal PowerShell :
```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```
*(Ou double-cliquez sur `run_backend.bat`)*

### 3. Démarrer le Frontend Multi-Espaces (React + Vite)
Dans un deuxième terminal :
```powershell
cd frontend
npm install
npm run dev
```
*(Ou double-cliquez sur `run_frontend.bat`)*

Ouvrez ensuite votre navigateur sur **http://localhost:5173**.

---

## 📡 Endpoints API REST Partagés

| Méthode | Endpoint | Description | Responsable |
|---|---|---|---|
| `GET` | `/api/urgences/alertes/` | Liste des alertes d'accidents récentes | Étudiant 3 |
| `GET` | `/api/urgences/geo-config/` | Configuration géographique centralisée du Nord-Est Cap Bon (centre, zoom, limites, localités) | Architecture |
| `GET` | `/api/urgences/casernes/` | Liste des casernes de pompiers du Nord-Est Cap Bon (Kélibia, Hammam El Ghezaz, El Haouaria, Azmour / Menzel Horr) | Étudiant 3 |
| `POST` | `/api/urgences/simuler-accident/` | Déclenche un accident test et diffuse l'alerte en direct | Étudiant 3 |
| `POST` | `/api/urgences/recevoir-accident/` | **Passerelle d'intégration :** Reçoit les signalements citoyens | Étud 2 ➔ Étud 3 |
| `POST` | `/api/urgences/alerte/{id}/statut/` | Met à jour le statut (`PRISE_EN_CHARGE`, `EN_INTERVENTION`, `CLOTURE`) | Étudiant 3 |
| `POST` | `/api/urgences/risk-map/` | Calcul du score de risque routier par Random Forest | Étudiant 3 |
| `WS` | `/ws/protection-civile/` | WebSocket Django Channels pour les alertes en direct (< 5s) | Étudiant 3 |

---

## 🚦 Simulateur de Trafic Autonome (Alternative à Google Maps Traffic)

Pour pallier l'absence ou la limitation de facturation de l'API Google Maps Traffic, un **simulateur de circulation métropolitaine autonome** a été développé dans le projet séparé [`smartcity-traffic-simulator`](../smartcity-traffic-simulator/) :

- **Port d'exécution :** `http://localhost:8001`
- **Console Web de Contrôle :** `http://localhost:8001/`
- **Documentation OpenAPI (Swagger) :** `http://localhost:8001/docs`
- **Intégration directe :**
  - **Carte Leaflet (`GoogleMapComponent.tsx`)** : Affichage des polylignes des 8 axes routiers du Nord-Est Cap Bon (Vert, Orange, Rouge, Bloqué) avec vitesse en direct et infobulles interactives lors de l'activation du bouton *Trafic Direct*.
  - **Calcul d'Itinéraire d'Urgence (`RoutePanel.tsx`)** : Calcul en temps réel de la durée de trajet et du retard effectif selon les tronçons traversés par l'ambulance.
  - **Modèle IA Risk Map (`RiskMapModal.tsx`)** : Bouton d'auto-synchronisation de l'indice de trafic (`trafic_index`) pour la prédiction Random Forest.
  - **Passerelle Django (`urgences/views.py`)** : Déclaration automatique d'un bouchon d'accident au simulateur lors d'une alerte et déblocage progressif à la clôture.

### Lancement du simulateur :
```bash
cd ../smartcity-traffic-simulator
./run_simulator.sh    # ou run_simulator.bat sous Windows
```

---

## 🗺️ Configuration Google Maps & Routes API (Optionnelle)

1. Obtenez une clé API sur la **Google Cloud Console**.
2. Activez **Maps JavaScript API** et **Routes API** (ou **Directions API**).
3. Ajoutez la clé dans `frontend/.env` :
   ```env
   VITE_GOOGLE_MAPS_API_KEY=AIzaSy...
   ```
*(En l'absence de clé, la cartographie Leaflet + OpenStreetMap couplée au simulateur de trafic autonome prend automatiquement le relais).*
