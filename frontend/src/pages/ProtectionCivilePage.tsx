import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getGeoConfig } from '../config/geoConfig';
import { Header } from '../components/Header';
import { AlertsList } from '../components/AlertsList';
import { GoogleMapComponent } from '../components/GoogleMapComponent';
import { RoutePanel } from '../components/RoutePanel';
import { RiskMapModal } from '../components/RiskMapModal';
import {
  fetchAlertes,
  fetchCasernes,
  updateStatutAlerte,
  simulerAccident,
  WS_BASE_URL,
  getActiveSession,
} from '../services/api';
import { playEmergencyAlarm, toggleSound, isSoundEnabled } from '../services/sound';
import type { Alerte, Caserne, RouteInfo, StatutAlerte } from '../types';
import { Flame, X } from 'lucide-react';

export const ProtectionCivilePage: React.FC = () => {
  const [alertes, setAlertes] = useState<Alerte[]>([]);
  const [casernes, setCasernes] = useState<Caserne[]>([]);
  const [selectedAlerte, setSelectedAlerte] = useState<Alerte | null>(null);
  const [selectedCaserne, setSelectedCaserne] = useState<Caserne | null>(null);
  const [activeRoute, setActiveRoute] = useState<RouteInfo | null>(null);

  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [soundActive, setSoundActive] = useState<boolean>(isSoundEnabled());
  const [trafficActive, setTrafficActive] = useState<boolean>(true);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [isRiskMapModalOpen, setIsRiskMapModalOpen] = useState<boolean>(false);

  // Notification visuelle prioritaire WebSocket
  const [priorityNotification, setPriorityNotification] = useState<{
    alerte: Alerte;
    timer: number;
  } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);

  // Vérification de session et permissions
  const session = getActiveSession();

  // Charger les alertes et les casernes initiales
  const loadInitialData = useCallback(async () => {
    try {
      const [alertesData, casernesData] = await Promise.all([
        fetchAlertes(),
        fetchCasernes(),
      ]);
      setAlertes(alertesData);
      setCasernes(casernesData);

      // Présélection de l'alerte active la plus urgente
      const activeAlert = alertesData.find(
        (a) => a.statut === 'CONFIRME' || a.statut === 'PRISE_EN_CHARGE'
      );
      if (activeAlert) {
        setSelectedAlerte(activeAlert);
      }
    } catch (err) {
      console.error('Erreur chargement initial:', err);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Rafraîchissement automatique des alertes et de la carte toutes les 30 secondes
  useEffect(() => {
    const refreshMapData = async () => {
      try {
        const [alertesData, casernesData] = await Promise.all([
          fetchAlertes(),
          fetchCasernes(),
        ]);
        setAlertes(alertesData);
        setCasernes(casernesData);
        setSelectedAlerte((prev) => {
          if (!prev) return null;
          const updated = alertesData.find((a) => a.id === prev.id);
          if (!updated || updated.statut === 'CLOTURE') return null;
          return updated;
        });
      } catch (err) {
        console.error('Erreur rafraîchissement carte (30s):', err);
      }
    };

    const intervalId = window.setInterval(refreshMapData, 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  // Connexion WebSocket en direct (< 5s)
  useEffect(() => {
    let isMounted = true;

    function connectWebSocket() {
      if (wsRef.current) {
        wsRef.current.close();
      }

      console.log('Connexion au WebSocket:', WS_BASE_URL);
      const ws = new WebSocket(WS_BASE_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        console.log('WebSocket Protection Civile connecté avec succès ✅');
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const data = JSON.parse(event.data);
          console.log('Message WebSocket reçu :', data);

          if (data.event === 'NOUVELLE_ALERTE_ACCIDENT' && data.alerte) {
            const rawAlerte = data.alerte;
            const formattedAlerte: Alerte = {
              id: rawAlerte.id,
              statut: rawAlerte.statut,
              gravite: rawAlerte.gravite,
              adresse: rawAlerte.adresse,
              latitude: Number(rawAlerte.latitude),
              longitude: Number(rawAlerte.longitude),
              nb_signalements: rawAlerte.nb_signalements || 1,
              date_confirmation: rawAlerte.date_confirmation,
              date_creation: rawAlerte.date_creation || new Date().toISOString(),
            };

            // 1. Déclencher la sirène sonore d'urgence
            playEmergencyAlarm();

            // 2. Notification visuelle prioritaire avec code couleur selon la gravité
            setPriorityNotification({
              alerte: formattedAlerte,
              timer: 10,
            });

            // 3. Mettre à jour la file des alertes
            setAlertes((prev) => {
              const exists = prev.findIndex((a) => a.id === formattedAlerte.id);
              if (exists >= 0) {
                const updated = [...prev];
                updated[exists] = { ...updated[exists], ...formattedAlerte };
                return updated;
              }
              return [formattedAlerte, ...prev];
            });

            // 4. Focus automatique et calcul immédiat de l'itinéraire vers la nouvelle alerte !
            setSelectedAlerte(formattedAlerte);
          } else if (data.event === 'STATUT_MIS_A_JOUR' && data.alerte) {
            const upd = data.alerte;
            setAlertes((prev) =>
              prev.map((a) =>
                a.id === upd.id
                  ? {
                      ...a,
                      statut: upd.statut,
                      date_prise_en_charge: upd.date_prise_en_charge || a.date_prise_en_charge,
                      date_en_intervention: upd.date_en_intervention || a.date_en_intervention,
                      date_cloture: upd.date_cloture || a.date_cloture,
                    }
                  : a
              )
            );
          }
        } catch (err) {
          console.error('Erreur parsing WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        console.warn('WebSocket déconnecté, tentative de reconnexion dans 3s...');
        setWsConnected(false);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (err) => {
        console.error('Erreur WebSocket :', err);
        ws.close();
      };
    }

    connectWebSocket();

    return () => {
      isMounted = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Actions
  const handleUpdateStatut = async (id: number, nouveauStatut: StatutAlerte, note?: string) => {
    try {
      const res = await updateStatutAlerte(id, nouveauStatut, {
        note: note || `Statut passé à ${nouveauStatut} depuis le poste de commandement`,
        matricule: session?.matricule_agent || session?.username || 'OP-198',
      });
      setAlertes((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, statut: res.nouveau_statut as StatutAlerte } : a
        )
      );
      if (selectedAlerte?.id === id) {
        if (nouveauStatut === 'CLOTURE') {
          setSelectedAlerte(null);
          setActiveRoute(null);
        } else {
          setSelectedAlerte((prev) =>
            prev ? { ...prev, statut: res.nouveau_statut as StatutAlerte } : null
          );
        }
      }
    } catch (err) {
      console.error('Erreur mise à jour statut:', err);
    }
  };

  const handleSimulateAccident = async () => {
    setSimulating(true);
    try {
      const res = await simulerAccident();
      if (res && res.alerte_id) {
        const simulatedAlerte: Alerte = {
          id: res.alerte_id,
          statut: res.statut || 'CONFIRME',
          gravite: res.gravite || 'GRAVE',
          adresse: res.adresse || getGeoConfig().default_city,
          latitude: Number(res.latitude),
          longitude: Number(res.longitude),
          nb_signalements: 1,
          date_confirmation: res.date_confirmation || new Date().toISOString(),
          date_creation: new Date().toISOString(),
        };

        setAlertes((prev) => {
          const exists = prev.findIndex((a) => a.id === simulatedAlerte.id);
          if (exists >= 0) {
            const updated = [...prev];
            updated[exists] = { ...updated[exists], ...simulatedAlerte };
            return updated;
          }
          return [simulatedAlerte, ...prev];
        });
        setSelectedAlerte(simulatedAlerte);
        playEmergencyAlarm();
      }
    } catch (err) {
      console.error('Erreur simulation accident:', err);
    } finally {
      setTimeout(() => setSimulating(false), 800);
    }
  };

  const handleSelectAlerte = (alerte: Alerte) => {
    setSelectedAlerte(alerte);
  };

  const handleTracerItineraire = (alerte: Alerte) => {
    setSelectedAlerte(alerte);
  };

  const handleToggleSound = () => {
    const next = toggleSound();
    setSoundActive(next);
  };

  const activeAlertsCount = alertes.filter(
    (a) => a.statut === 'CONFIRME' || a.statut === 'PRISE_EN_CHARGE' || a.statut === 'EN_INTERVENTION'
  ).length;

  // Code couleur de gravité pour la bannière prioritaire
  const getSeverityStyle = (gravite?: string) => {
    if (gravite === 'GRAVE' || gravite === 'CRITIQUE') {
      return {
        bg: 'linear-gradient(90deg, rgba(239, 68, 68, 0.95), rgba(185, 28, 28, 0.95))',
        border: '#ef4444',
        badge: 'URGENCE CRITIQUE',
        badgeBg: '#7f1d1d',
      };
    }
    if (gravite === 'MOYENNE') {
      return {
        bg: 'linear-gradient(90deg, rgba(245, 158, 11, 0.95), rgba(180, 83, 9, 0.95))',
        border: '#f59e0b',
        badge: 'URGENCE ÉLEVÉE',
        badgeBg: '#78350f',
      };
    }
    return {
      bg: 'linear-gradient(90deg, rgba(56, 189, 248, 0.95), rgba(3, 105, 161, 0.95))',
      border: '#38bdf8',
      badge: 'VIGILANCE MODÉRÉE',
      badgeBg: '#082f49',
    };
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', overflow: 'hidden' }}>
      {/* Header bar opérationnel */}
      <Header
        wsConnected={wsConnected}
        soundEnabled={soundActive}
        onToggleSound={handleToggleSound}
        trafficLayerActive={trafficActive}
        onToggleTraffic={() => setTrafficActive(!trafficActive)}
        onOpenRiskMapModal={() => setIsRiskMapModalOpen(true)}
        onSimulateAccident={handleSimulateAccident}
        simulating={simulating}
        activeCount={activeAlertsCount}
      />

      {/* Notification Visuelle Prioritaire WebSocket (< 5s) avec code couleur selon gravité */}
      {priorityNotification && (
        <div
          style={{
            background: getSeverityStyle(priorityNotification.alerte.gravite).bg,
            borderBottom: `2px solid ${getSeverityStyle(priorityNotification.alerte.gravite).border}`,
            padding: '10px 24px',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 4px 20px rgba(239, 68, 68, 0.4)',
            zIndex: 90,
            animation: 'pulse 1.5s infinite',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span
              style={{
                background: getSeverityStyle(priorityNotification.alerte.gravite).badgeBg,
                color: '#fff',
                fontSize: 11,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 20,
                letterSpacing: '0.5px',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Flame size={14} /> {getSeverityStyle(priorityNotification.alerte.gravite).badge}
            </span>
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              <span>🚨 NOUVEL ACCIDENT SIGNALÉ (&lt; 5s) : </span>
              <strong style={{ textDecoration: 'underline' }}>{priorityNotification.alerte.adresse}</strong>
              <span style={{ opacity: 0.9, marginLeft: 8 }}>
                ({priorityNotification.alerte.nb_signalements} signalement(s) concordant(s) PostGIS)
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              type="button"
              onClick={() => {
                setSelectedAlerte(priorityNotification.alerte);
                setPriorityNotification(null);
              }}
              style={{
                backgroundColor: '#fff',
                color: '#b91c1c',
                border: 'none',
                borderRadius: 6,
                padding: '6px 14px',
                fontWeight: 700,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              📍 Afficher l'itinéraire immédiat
            </button>
            <button
              type="button"
              onClick={() => setPriorityNotification(null)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#fff',
                cursor: 'pointer',
                opacity: 0.8,
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Disposition ergonomique en 3 colonnes : File d'Alertes | Carte Plein Écran | Panneau d'Itinéraire */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative' }}>
        {/* Colonne 1 : File des Alertes & Incidents */}
        <AlertsList
          alertes={alertes}
          selectedAlerte={selectedAlerte}
          onSelectAlerte={handleSelectAlerte}
          onUpdateStatut={handleUpdateStatut}
          onTracerItineraire={handleTracerItineraire}
        />

        {/* Colonne 2 : Carte Tactique Plein Écran */}
        <div style={{ flex: 1, position: 'relative', height: '100%', minWidth: 0, overflow: 'hidden' }}>
          <GoogleMapComponent
            casernes={casernes}
            alertes={alertes}
            selectedAlerte={selectedAlerte}
            selectedCaserne={selectedCaserne}
            trafficLayerActive={trafficActive}
            onSelectAlerte={handleSelectAlerte}
            onRouteCalculated={setActiveRoute}
          />
        </div>

        {/* Colonne 3 : Panneau d'Intervention d'Urgence */}
        {activeRoute && selectedAlerte && (
          <RoutePanel
            routeInfo={activeRoute}
            casernes={casernes}
            onSelectCaserne={(c) => setSelectedCaserne(c)}
            onClose={() => {
              setActiveRoute(null);
              setSelectedAlerte(null);
            }}
            onValiderIntervention={() => {
              handleUpdateStatut(selectedAlerte.id, 'EN_INTERVENTION', 'Validation départ pompiers depuis la carte');
              playEmergencyAlarm();
            }}
          />
        )}
      </div>

      {/* Modal Risk Map Machine Learning & Assistant IA Décisionnel */}
      <RiskMapModal
        isOpen={isRiskMapModalOpen}
        onClose={() => setIsRiskMapModalOpen(false)}
      />
    </div>
  );
};

