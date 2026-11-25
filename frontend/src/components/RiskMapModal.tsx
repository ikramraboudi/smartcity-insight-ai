import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  X,
  Bot,
  Sparkles,
  Send,
  Layers,
} from 'lucide-react';
import { getGeoConfig } from '../config/geoConfig';
import {
  fetchZonesRiskMap,
  askAssistantLLM,
} from '../services/api';
import type { ZoneRiskMap } from '../types';

interface RiskMapModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RiskMapModal: React.FC<RiskMapModalProps> = ({ isOpen, onClose }) => {
  const geoCfg = getGeoConfig();
  // Navigation par onglets : 'zones' | 'assistant'
  const [activeTab, setActiveTab] = useState<'zones' | 'assistant'>('zones');

  // État Onglet 1 : Secteurs régionaux
  const [zones, setZones] = useState<ZoneRiskMap[]>([]);
  const [loadingZones, setLoadingZones] = useState<boolean>(false);
  const [selectedZone, setSelectedZone] = useState<ZoneRiskMap | null>(null);

  // État Onglet 2 : Assistant LLM Décisionnel
  const [chatMessages, setChatMessages] = useState<
    Array<{ sender: 'user' | 'assistant'; text: string; moteur?: string }>
  >([
    {
      sender: 'assistant',
      text: `Bonjour. Je suis l'**Assistant IA Décisionnel** de la Protection Civile du ${geoCfg.region_name}.\nJe m'appuie strictement sur les données réelles (accidents BDD, congestion connectée, axes sensibles).\n\nPosez une question ou cliquez sur l'une des suggestions ci-dessous.`,
      moteur: 'RAG Strict Anti-Hallucination',
    },
  ]);
  const [questionInput, setQuestionInput] = useState<string>('');
  const [llmLoading, setLlmLoading] = useState<boolean>(false);

  // Charger les zones au montage et à l'ouverture
  useEffect(() => {
    if (isOpen) {
      setLoadingZones(true);
      fetchZonesRiskMap()
        .then((data) => {
          setZones(data);
          if (data.length > 0 && !selectedZone) {
            setSelectedZone(data[0]);
          }
        })
        .finally(() => setLoadingZones(false));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Envoi d'une question à l'Assistant LLM
  const handleAskQuestion = async (queryText?: string) => {
    const q = (queryText || questionInput).trim();
    if (!q || llmLoading) return;

    setQuestionInput('');
    setChatMessages((prev) => [...prev, { sender: 'user', text: q }]);
    setLlmLoading(true);

    try {
      const res = await askAssistantLLM(q);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: res.reponse,
          moteur: res.moteur,
        },
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: "Désolé, une indisponibilité temporaire empêche l'Assistant de répondre. Veuillez réessayer.",
        },
      ]);
    } finally {
      setLlmLoading(false);
    }
  };

  const getCouleurBadge = (couleur: 'vert' | 'orange' | 'rouge') => {
    switch (couleur) {
      case 'rouge':
        return { bg: 'rgba(239, 68, 68, 0.2)', border: '#ef4444', text: '#f87171', label: 'ÉLEVÉ (ROUGE)' };
      case 'orange':
        return { bg: 'rgba(245, 158, 11, 0.2)', border: '#f59e0b', text: '#fbbf24', label: 'MODÉRÉ (ORANGE)' };
      default:
        return { bg: 'rgba(16, 185, 129, 0.2)', border: '#10b981', text: '#34d399', label: 'FAIBLE (VERT)' };
    }
  };

  const suggestedQuestions = [
    "Quelles sont les zones rouges prioritaires ?",
    "Pourquoi El Haouaria ou Menzel Horr présente un risque élevé ?",
    "Quelles sont les alertes actives en cours ?",
    "Quelles casernes et ambulances sont disponibles ?",
  ];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        backdropFilter: 'blur(8px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #334155',
          borderRadius: '12px',
          width: '100%',
          maxWidth: '780px',
          height: '85vh',
          maxHeight: '740px',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
          overflow: 'hidden',
        }}
      >
        {/* Header Modale */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#090e1a',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ef4444',
                border: '1px solid rgba(239, 68, 68, 0.3)',
              }}
            >
              <ShieldAlert size={22} />
            </div>
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
                Centre Risk Map & Assistant IA Décisionnel
              </h3>
              <p style={{ fontSize: '11px', color: '#94a3b8', margin: 0 }}>
                {geoCfg.region_name} • Prédiction multi-sources (Accidents + Trafic + Géométrie)
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Barre d'onglets ergonomiques */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid #1e293b',
            backgroundColor: '#0b111e',
            padding: '0 16px',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('zones')}
            style={{
              padding: '12px 16px',
              border: 'none',
              background: 'none',
              color: activeTab === 'zones' ? '#38bdf8' : '#94a3b8',
              borderBottom: activeTab === 'zones' ? '2px solid #38bdf8' : '2px solid transparent',
              fontWeight: 700,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Layers size={16} />
            <span>Secteurs du {geoCfg.region_short_name} ({zones.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('assistant')}
            style={{
              padding: '12px 16px',
              border: 'none',
              background: 'none',
              color: activeTab === 'assistant' ? '#34d399' : '#94a3b8',
              borderBottom: activeTab === 'assistant' ? '2px solid #34d399' : '2px solid transparent',
              fontWeight: 700,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Bot size={16} />
            <span>Assistant IA Décisionnel (RAG)</span>
            <span
              style={{
                backgroundColor: 'rgba(52, 211, 153, 0.15)',
                color: '#34d399',
                fontSize: '10px',
                padding: '1px 6px',
                borderRadius: '10px',
              }}
            >
              Anti-Hallucination
            </span>
          </button>
        </div>

        {/* Corps des onglets */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          {/* ========================================================================= */}
          {/* ONGLET 1 : Cartographie des Secteurs réels du Cap Bon                     */}
          {/* ========================================================================= */}
          {activeTab === 'zones' && (
            <div>
              <div style={{ marginBottom: 14 }}>
                <h4 style={{ color: '#f8fafc', fontSize: 14, margin: '0 0 4px 0' }}>
                  Évaluation continue du risque routier sur le {geoCfg.region_short_name}
                </h4>
                <p style={{ color: '#94a3b8', fontSize: 12, margin: 0 }}>
                  Barème officiel : <span style={{ color: '#34d399' }}>Vert &lt; 35%</span> •{' '}
                  <span style={{ color: '#fbbf24' }}>Orange 35% – 69%</span> •{' '}
                  <span style={{ color: '#f87171' }}>Rouge ≥ 70%</span>
                </p>
              </div>

              {loadingZones ? (
                <div style={{ color: '#94a3b8', textAlign: 'center', padding: 40 }}>
                  Chargement des prédictions des secteurs...
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  {zones.map((z) => {
                    const badge = getCouleurBadge(z.niveau_couleur);
                    const isSelected = selectedZone?.zone_id === z.zone_id;

                    return (
                      <div
                        key={z.zone_id}
                        onClick={() => setSelectedZone(z)}
                        style={{
                          backgroundColor: isSelected ? 'rgba(30, 41, 59, 0.9)' : '#111a2d',
                          border: isSelected ? `2px solid ${badge.border}` : '1px solid #1e293b',
                          borderRadius: 8,
                          padding: 14,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                          <div>
                            <strong style={{ color: '#f8fafc', fontSize: 13, display: 'block' }}>
                              {z.zone_nom}
                            </strong>
                            <span style={{ color: '#64748b', fontSize: 11 }}>{z.type_troncon}</span>
                          </div>
                          <div
                            style={{
                              backgroundColor: badge.bg,
                              color: badge.text,
                              border: `1px solid ${badge.border}`,
                              borderRadius: 16,
                              padding: '2px 8px',
                              fontSize: 11,
                              fontWeight: 800,
                            }}
                          >
                            {z.score_risque_pourcentage}%
                          </div>
                        </div>

                        <div style={{ borderTop: '1px solid #1e293b', paddingTop: 8, marginTop: 8 }}>
                          <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, display: 'block', marginBottom: 4 }}>
                            Facteurs explicatifs principaux :
                          </span>
                          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11.5, color: '#cbd5e1' }}>
                            {z.facteurs_explicatifs.map((f, i) => (
                              <li key={i} style={{ marginBottom: 2 }}>{f}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* ONGLET 2 : Assistant IA Décisionnel RAG Strict (Anti-Hallucination)        */}
          {/* ========================================================================= */}
          {activeTab === 'assistant' && (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Messages Chat */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  paddingRight: 6,
                  marginBottom: 14,
                }}
              >
                {chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    style={{
                      alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                      maxWidth: '85%',
                      backgroundColor: msg.sender === 'user' ? '#1d4ed8' : '#111a2d',
                      border: msg.sender === 'user' ? '1px solid #2563eb' : '1px solid #1e293b',
                      borderRadius: 10,
                      padding: '12px 14px',
                      color: '#f8fafc',
                      fontSize: 12.5,
                      lineHeight: 1.5,
                    }}
                  >
                    {msg.sender === 'assistant' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, color: '#34d399', fontSize: 11, fontWeight: 700 }}>
                        <Sparkles size={13} />
                        <span>{msg.moteur || 'Assistant Décisionnel'}</span>
                      </div>
                    )}
                    <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                  </div>
                ))}

                {llmLoading && (
                  <div
                    style={{
                      alignSelf: 'flex-start',
                      backgroundColor: '#111a2d',
                      border: '1px solid #1e293b',
                      borderRadius: 10,
                      padding: '10px 14px',
                      color: '#94a3b8',
                      fontSize: 12,
                    }}
                  >
                    ⚡ Interrogation du contexte temps réel BDD en cours...
                  </div>
                )}
              </div>

              {/* Questions Suggérées */}
              <div style={{ marginBottom: 12 }}>
                <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                  Questions d'intervention suggérées :
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {suggestedQuestions.map((sq, i) => (
                    <button
                      key={i}
                      type="button"
                      disabled={llmLoading}
                      onClick={() => handleAskQuestion(sq)}
                      style={{
                        backgroundColor: 'rgba(30, 41, 59, 0.7)',
                        border: '1px solid #334155',
                        borderRadius: 14,
                        padding: '4px 10px',
                        fontSize: 11,
                        color: '#cbd5e1',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#38bdf8')}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#334155')}
                    >
                      💡 {sq}
                    </button>
                  ))}
                </div>
              </div>

              {/* Formulaire de saisie de question */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAskQuestion();
                }}
                style={{ display: 'flex', gap: 8 }}
              >
                <input
                  type="text"
                  placeholder={`Posez une question décisionnelle sur le réseau du ${geoCfg.region_short_name}...`}
                  value={questionInput}
                  onChange={(e) => setQuestionInput(e.target.value)}
                  style={{
                    flex: 1,
                    backgroundColor: '#111a2d',
                    border: '1px solid #1e293b',
                    borderRadius: 8,
                    padding: '10px 14px',
                    color: '#f8fafc',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
                <button
                  type="submit"
                  disabled={!questionInput.trim() || llmLoading}
                  style={{
                    backgroundColor: '#059669',
                    border: 'none',
                    borderRadius: 8,
                    padding: '0 18px',
                    color: '#fff',
                    fontWeight: 700,
                    cursor: questionInput.trim() && !llmLoading ? 'pointer' : 'not-allowed',
                    opacity: questionInput.trim() && !llmLoading ? 1 : 0.6,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <Send size={15} />
                  <span>Envoyer</span>
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
