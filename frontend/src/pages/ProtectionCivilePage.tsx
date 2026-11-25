import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  triggerSimulation,
  WS_BASE_URL,
  getActiveSession,
} from '../services/api';
import { playEmergencyAlarm, toggleSound, isSoundEnabled } from '../services/sound';
import type { Alerte, Caserne, RouteInfo, StatutAlerte, SimulationResult } from '../types';
import { AlertCircle, Bot, CheckCircle2, ChevronDown, ChevronUp, Flame, ShieldAlert, Sparkles, TestTube2, Volume2, X } from 'lucide-react';

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

  // Mode Simulation Jury
  const [showSimuPanel, setShowSimuPanel] = useState<boolean>(true);
  const [simulationLoading, setSimulationLoading] = useState<boolean>(false);
  const [lastSimuResult, setLastSimuResult] = useState<SimulationResult | null>(null);

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
          adresse: res.adresse || 'Tunis Centre',
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

  const handleRunSimulationJury = async (mode: 'fausse_alerte' | 'accident_confirme' | 'risk_map') => {
    setSimulationLoading(true);
    try {
      const res = await triggerSimulation(mode);
      setLastSimuResult(res);

      if (mode === 'accident_confirme') {
        playEmergencyAlarm();
        // Recharger les alertes pour voir l'accident confirmé fusionné
        await loadInitialData();
      } else if (mode === 'risk_map') {
        setIsRiskMapModalOpen(true);
      }
    } catch (err) {
      console.error('Erreur exécution simulation jury:', err);
    } finally {
      setSimulationLoading(false);
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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
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

          {/* Panneau Flottant « 🧪 Mode Simulation Jury » (Démo 1 Clic pour la Soutenance) */}
          <div
            style={{
              position: 'absolute',
              bottom: 20,
              left: 20,
              zIndex: 35,
              backgroundColor: 'rgba(15, 23, 42, 0.95)',
              backdropFilter: 'blur(8px)',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              borderRadius: 10,
              padding: showSimuPanel ? '12px 16px' : '8px 12px',
              maxWidth: 420,
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.6)',
              transition: 'all 0.2s ease',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
              }}
              onClick={() => setShowSimuPanel(!showSimuPanel)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#38bdf8', fontWeight: 700, fontSize: 13 }}>
                <TestTube2 size={16} />
                <span>🧪 Mode Simulation Jury (Démo Live)</span>
              </div>
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
              >
                {showSimuPanel ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
              </button>
            </div>

            {showSimuPanel && (
              <div style={{ marginTop: 10 }}>
                <p style={{ fontSize: 11, color: '#94a3b8', margin: '0 0 10px 0' }}>
                  Déclenchez en direct les scénarios clés exigés par le cahier des charges :
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 6 }}>
                  {/* Bouton Simulation 1 : Anti-Fausse Alerte */}
                  <button
                    type="button"
                    disabled={simulationLoading}
                    onClick={() => handleRunSimulationJury('fausse_alerte')}
                    style={{
                      background: 'rgba(100, 116, 139, 0.15)',
                      border: '1px solid #475569',
                      borderRadius: 6,
                      color: '#cbd5e1',
                      padding: '6px 10px',
                      fontSize: 11.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#94a3b8')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#475569')}
                  >
                    <span>🛡️</span>
                    <div>
                      <strong>1. Test Anti-Fausse Alerte</strong>
                      <div style={{ fontSize: 10, color: '#94a3b8' }}>1 signalement isolé → en attente, pas de sirène</div>
                    </div>
                  </button>

                  {/* Bouton Simulation 2 : Fusion PostGIS & Diffusion < 5s */}
                  <button
                    type="button"
                    disabled={simulationLoading}
                    onClick={() => handleRunSimulationJury('accident_confirme')}
                    style={{
                      background: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      borderRadius: 6,
                      color: '#fca5a5',
                      padding: '6px 10px',
                      fontSize: 11.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#ef4444')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(239, 68, 68, 0.4)')}
                  >
                    <span>🚨</span>
                    <div>
                      <strong>2. Clustering PostGIS (&lt; 5s)</strong>
                      <div style={{ fontSize: 10, color: '#f87171' }}>3 signalements concordants → sirène & tracé live</div>
                    </div>
                  </button>

                  {/* Bouton Simulation 3 : Générer Risk Map */}
                  <button
                    type="button"
                    disabled={simulationLoading}
                    onClick={() => handleRunSimulationJury('risk_map')}
                    style={{
                      background: 'rgba(16, 185, 129, 0.15)',
                      border: '1px solid rgba(16, 185, 129, 0.4)',
                      borderRadius: 6,
                      color: '#6ee7b7',
                      padding: '6px 10px',
                      fontSize: 11.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#10b981')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(16, 185, 129, 0.4)')}
                  >
                    <span>🗺️</span>
                    <div>
                      <strong>3. Scénario Risk Map Tunis</strong>
                      <div style={{ fontSize: 10, color: '#34d399' }}>Secteurs vert, orange, rouge & Assistant IA</div>
                    </div>
                  </button>
                </div>

                {/* Résultat du dernier test */}
                {lastSimuResult && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: '8px 10px',
                      borderRadius: 6,
                      background: 'rgba(30, 41, 59, 0.8)',
                      border: '1px solid #334155',
                      fontSize: 11,
                      color: '#e2e8f0',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#38bdf8', fontWeight: 700 }}>
                      <CheckCircle2 size={13} />
                      <span>{lastSimuResult.scenario}</span>
                    </div>
                    <div style={{ marginTop: 4, color: '#cbd5e1' }}>{lastSimuResult.message}</div>
                  </div>
                )}
              </div>
            )}
          </div>
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

