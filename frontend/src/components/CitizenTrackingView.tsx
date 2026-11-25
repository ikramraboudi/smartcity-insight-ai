import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import {
  CheckCircle2,
  Clock,
  Filter,
  Flame,
  Loader2,
  MapPin,
  RefreshCw,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import {
  addStandardBasemapLayer,
  getGeoConfig,
  getRegionLeafletBounds,
  renderLocalityLabelsLayer,
} from '../config/geoConfig';
import { BACKEND_URL, getActiveSession, getSavedCitizenReportIds, getSignalements } from '../services/api';
import { CategorieSignalement, Signalement, StatutSignalement } from '../types';

const CATEGORIE_INFO: Record<CategorieSignalement, { label: string; icon: string; color: string }> = {
  ACCIDENT: { label: 'Accident', icon: '💥', color: '#ef4444' },
  NID_DE_POULE: { label: 'Nid-de-poule', icon: '🕳️', color: '#f59e0b' },
  ECLAIRAGE: { label: 'Éclairage public', icon: '💡', color: '#eab308' },
  DECHETS: { label: 'Déchets / Voirie', icon: '🗑️', color: '#10b981' },
  SIGNALISATION: { label: 'Signalisation', icon: '🛑', color: '#f97316' },
  AUTRE: { label: 'Autre', icon: '⚠️', color: '#38bdf8' },
};

const STATUT_STEPS: { key: StatutSignalement; label: string }[] = [
  { key: 'EN_ATTENTE', label: 'En attente' },
  { key: 'CONFIRME', label: 'Confirmé' },
  { key: 'EN_COURS', label: 'En cours' },
  { key: 'RESOLU', label: 'Résolu' },
];

const STATUT_BADGE: Record<StatutSignalement, { label: string; color: string; bg: string }> = {
  EN_ATTENTE: { label: 'En attente', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' },
  CONFIRME: { label: 'Confirmé', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.15)' },
  EN_COURS: { label: 'En cours', color: '#06b6d4', bg: 'rgba(6, 182, 212, 0.15)' },
  RESOLU: { label: 'Résolu', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)' },
  REJETE_SPAM: { label: 'Rejeté / Spam', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)' },
};

interface CitizenTrackingViewProps {
  highlightReportId?: string | null;
}

export const CitizenTrackingView: React.FC<CitizenTrackingViewProps> = ({ highlightReportId }) => {
  const [signalements, setSignalements] = useState<Signalement[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [onlyMine, setOnlyMine] = useState(false);
  const [filterCategorie, setFilterCategorie] = useState('TOUS');
  const [filterStatut, setFilterStatut] = useState('TOUS');
  const [selectedId, setSelectedId] = useState<string | null>(highlightReportId || null);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const markerByIdRef = useRef<Record<string, L.Marker>>({});

  const session = getActiveSession();
  const hasJwtToken = Boolean(session?.token);

  const isMyReport = useCallback(
    (s: Signalement) => {
      const savedIds = getSavedCitizenReportIds();
      return Boolean(s.est_mon_signalement) || savedIds.includes(s.id);
    },
    []
  );

  const loadReports = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await getSignalements({
        categorie: filterCategorie !== 'TOUS' ? filterCategorie : undefined,
        statut: filterStatut !== 'TOUS' ? filterStatut : undefined,
        mes_signalements: onlyMine && hasJwtToken ? true : undefined,
      });
      setSignalements(data);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Impossible de charger la carte des signalements.');
    } finally {
      setIsLoading(false);
    }
  }, [filterCategorie, filterStatut, onlyMine, hasJwtToken]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) {
        void loadReports();
      }
    });
    return () => {
      cancelled = true;
    };
  }, [loadReports]);

  const displayedSignalements = useMemo(() => {
    if (!onlyMine) return signalements;
    return signalements.filter((s) => isMyReport(s));
  }, [signalements, onlyMine, isMyReport]);

  // Initialisation de la carte Leaflet publique
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const geoCfg = getGeoConfig();
    const regionBounds = getRegionLeafletBounds(geoCfg);
    const map = L.map(mapContainerRef.current, {
      center: geoCfg.map.center,
      zoom: geoCfg.map.zoom,
      minZoom: geoCfg.map.min_zoom,
      maxZoom: geoCfg.map.max_zoom,
      maxBounds: regionBounds,
      maxBoundsViscosity: 1.0,
    });

    addStandardBasemapLayer(map);

    const labelsLayer = L.layerGroup().addTo(map);
    renderLocalityLabelsLayer(labelsLayer, geoCfg.delegations);

    markersLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(mapContainerRef.current);
    const t = setTimeout(() => {
      map.invalidateSize();
      map.fitBounds(regionBounds, { padding: [20, 20] });
    }, 150);

    return () => {
      clearTimeout(t);
      ro.disconnect();
      map.remove();
      mapRef.current = null;
      markersLayerRef.current = null;
    };
  }, []);

  // Synchronisation des marqueurs sur la carte Leaflet
  useEffect(() => {
    if (!mapRef.current || !markersLayerRef.current) return;
    markersLayerRef.current.clearLayers();
    markerByIdRef.current = {};

    displayedSignalements.forEach((s) => {
      const cat = CATEGORIE_INFO[s.categorie] || CATEGORIE_INFO.AUTRE;
      const statutMeta = STATUT_BADGE[s.statut] || STATUT_BADGE.EN_ATTENTE;
      const mine = isMyReport(s);
      const isSelected = selectedId === s.id;

      const icon = L.divIcon({
        className: 'citizen-map-marker',
        html: `<div style="
          width: ${isSelected ? 36 : 30}px;
          height: ${isSelected ? 36 : 30}px;
          border-radius: 50%;
          background: ${s.statut === 'RESOLU' ? '#059669' : cat.color};
          border: ${mine ? '3px solid #34d399' : isSelected ? '3px solid #fff' : '2px solid rgba(255,255,255,0.85)'};
          box-shadow: 0 0 ${isSelected ? '16px' : '10px'} ${cat.color}88;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: ${isSelected ? 17 : 14}px;
          cursor: pointer;
          transition: transform 0.15s ease;
        ">${cat.icon}</div>`,
        iconSize: [isSelected ? 36 : 30, isSelected ? 36 : 30],
        iconAnchor: [isSelected ? 18 : 15, isSelected ? 18 : 15],
      });

      const photoUrl = s.photo_floutee
        ? s.photo_floutee.startsWith('http')
          ? s.photo_floutee
          : `${BACKEND_URL}${s.photo_floutee.startsWith('/') ? '' : '/'}${s.photo_floutee}`
        : null;

      const marker = L.marker([s.latitude, s.longitude], { icon });
      marker.bindPopup(`
        <div style="font-family: Inter, sans-serif; color: #f8fafc; min-width: 210px; max-width: 250px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:6px;">
            <strong style="font-size:13px;">${cat.icon} ${cat.label}</strong>
            <span style="font-size:10.5px; font-weight:700; padding:2px 7px; border-radius:8px; background:${statutMeta.bg}; color:${statutMeta.color};">
              ${statutMeta.label}
            </span>
          </div>
          ${photoUrl ? `<img src="${photoUrl}" alt="Photo INPDP" style="width:100%; height:95px; object-fit:cover; border-radius:6px; margin-bottom:6px; border:1px solid #334155;" />` : ''}
          <p style="font-size:12px; color:#cbd5e1; margin:0 0 6px 0; line-height:1.35;">${s.description || 'Signalement citoyen'}</p>
          <div style="font-size:11px; color:#94a3b8;">📍 ${s.quartier}${s.adresse_texte ? ` • ${s.adresse_texte}` : ''}</div>
          ${s.visages_plaques_floutes ? `<div style="font-size:10.5px; color:#34d399; margin-top:4px;">🛡️ Anonymisé INPDP</div>` : ''}
        </div>
      `);

      marker.on('click', () => {
        setSelectedId(s.id);
      });

      marker.addTo(markersLayerRef.current!);
      markerByIdRef.current[s.id] = marker;
    });
  }, [displayedSignalements, selectedId, isMyReport]);

  const handleFocusSignalement = (s: Signalement) => {
    setSelectedId(s.id);
    if (mapRef.current) {
      mapRef.current.setView([s.latitude, s.longitude], 15, { animate: true });
      const m = markerByIdRef.current[s.id];
      if (m) m.openPopup();
    }
  };

  const getStepIndex = (statut: StatutSignalement) => {
    const idx = STATUT_STEPS.findIndex((st) => st.key === statut);
    return idx >= 0 ? idx : 0;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Barre de filtres */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 14,
          padding: '14px 16px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-muted)' }}>
            <Filter size={15} /> Filtres :
          </div>

          <button
            type="button"
            onClick={() => setOnlyMine((v) => !v)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 12px',
              borderRadius: 8,
              fontSize: 12.5,
              fontWeight: 600,
              cursor: 'pointer',
              background: onlyMine ? 'rgba(16, 185, 129, 0.18)' : 'var(--bg-dark)',
              border: `1px solid ${onlyMine ? '#10b981' : 'var(--border-color)'}`,
              color: onlyMine ? '#34d399' : 'var(--text-muted)',
            }}
          >
            <UserCheck size={14} />
            <span>Mes signalements uniquement</span>
          </button>

          <select
            value={filterCategorie}
            onChange={(e) => setFilterCategorie(e.target.value)}
            style={{
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: '7px 10px',
              color: 'var(--text-main)',
              fontSize: 12.5,
            }}
          >
            <option value="TOUS">Toutes catégories</option>
            <option value="ACCIDENT">Accident</option>
            <option value="NID_DE_POULE">Nid-de-poule</option>
            <option value="ECLAIRAGE">Éclairage public</option>
            <option value="DECHETS">Déchets / Voirie</option>
            <option value="SIGNALISATION">Signalisation</option>
            <option value="AUTRE">Autre</option>
          </select>

          <select
            value={filterStatut}
            onChange={(e) => setFilterStatut(e.target.value)}
            style={{
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: '7px 10px',
              color: 'var(--text-main)',
              fontSize: 12.5,
            }}
          >
            <option value="TOUS">Tous les statuts</option>
            <option value="EN_ATTENTE">En attente</option>
            <option value="CONFIRME">Confirmé</option>
            <option value="EN_COURS">En cours</option>
            <option value="RESOLU">Résolu</option>
          </select>
        </div>

        <button
          type="button"
          onClick={loadReports}
          disabled={isLoading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(56, 189, 248, 0.12)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            color: '#38bdf8',
            borderRadius: 8,
            padding: '7px 12px',
            fontSize: 12.5,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          <span>Actualiser ({displayedSignalements.length})</span>
        </button>
      </div>

      {errorMsg && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.14)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: '#fca5a5',
            borderRadius: 10,
            padding: '10px 14px',
            fontSize: 13,
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* Disposition responsive Carte Leaflet + Liste de suivi */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 18,
          alignItems: 'start',
        }}
      >
        {/* Carte publique Leaflet */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: 14,
            overflow: 'hidden',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.28)',
          }}
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'var(--bg-dark)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, fontWeight: 700 }}>
              <MapPin size={16} color="#38bdf8" />
              <span>Carte Citoyenne du {getGeoConfig().region_short_name}</span>
            </div>
            <span style={{ fontSize: 11.5, color: 'var(--text-dim)' }}>
              {displayedSignalements.length} incident(s)
            </span>
          </div>
          <div ref={mapContainerRef} style={{ width: '100%', height: 420, backgroundColor: '#0b111e' }} />
        </div>

        {/* Liste de suivi d'avancement avec barre de progression visuelle */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: 14,
            padding: 16,
            maxHeight: 468,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, fontWeight: 700 }}>
              <Clock size={16} color="#10b981" />
              <span>Suivi d'Avancement en Temps Réel</span>
            </div>
            {isLoading && <Loader2 size={15} className="animate-spin" color="#38bdf8" />}
          </div>

          {displayedSignalements.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
              {onlyMine
                ? "Vous n'avez pas encore de signalement correspondant à ces filtres."
                : 'Aucun signalement public trouvé pour ces critères.'}
            </div>
          ) : (
            displayedSignalements.map((s) => {
              const cat = CATEGORIE_INFO[s.categorie] || CATEGORIE_INFO.AUTRE;
              const badge = STATUT_BADGE[s.statut] || STATUT_BADGE.EN_ATTENTE;
              const mine = isMyReport(s);
              const isSelected = selectedId === s.id;
              const stepIdx = getStepIndex(s.statut);

              return (
                <div
                  key={s.id}
                  onClick={() => handleFocusSignalement(s)}
                  style={{
                    background: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'var(--bg-dark)',
                    border: `1px solid ${isSelected ? '#38bdf8' : mine ? 'rgba(16, 185, 129, 0.35)' : 'var(--border-color)'}`,
                    borderRadius: 12,
                    padding: 14,
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 15 }}>{cat.icon}</span>
                    <strong style={{ fontSize: 13.5, color: 'var(--text-main)' }}>{cat.label}</strong>

                    {mine && (
                      <span
                        style={{
                          fontSize: 10.5,
                          fontWeight: 700,
                          color: '#34d399',
                          background: 'rgba(16, 185, 129, 0.15)',
                          border: '1px solid rgba(16, 185, 129, 0.35)',
                          padding: '1px 7px',
                          borderRadius: 10,
                        }}
                      >
                        Mon signalement
                      </span>
                    )}

                    {s.alerte_liee && (
                      <span
                        style={{
                          fontSize: 10.5,
                          fontWeight: 700,
                          color: '#f87171',
                          background: 'rgba(239, 68, 68, 0.15)',
                          padding: '1px 7px',
                          borderRadius: 10,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 3,
                        }}
                      >
                        <Flame size={10} /> Secours #{s.alerte_liee}
                      </span>
                    )}

                    <span
                      style={{
                        marginLeft: 'auto',
                        fontSize: 11,
                        fontWeight: 700,
                        color: badge.color,
                        background: badge.bg,
                        padding: '2px 8px',
                        borderRadius: 10,
                      }}
                    >
                      {badge.label}
                    </span>
                  </div>

                  <p style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.4 }}>
                    {s.description || 'Signalement sans description.'}
                  </p>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, fontSize: 11, color: 'var(--text-dim)', marginBottom: 10 }}>
                    <span>📍 {s.quartier}</span>
                    <span>•</span>
                    <span>{new Date(s.date_creation).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
                    {s.visages_plaques_floutes && (
                      <>
                        <span>•</span>
                        <span style={{ color: '#34d399', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                          <ShieldCheck size={11} /> INPDP
                        </span>
                      </>
                    )}
                  </div>

                  {/* Barre de progression visuelle des 4 étapes */}
                  {s.statut !== 'REJETE_SPAM' ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4 }}>
                      {STATUT_STEPS.map((st, idx) => {
                        const reached = idx <= stepIdx;
                        const active = idx === stepIdx;
                        const barColor =
                          s.statut === 'RESOLU'
                            ? '#10b981'
                            : active
                            ? '#38bdf8'
                            : reached
                            ? '#0ea5e9'
                            : 'rgba(255, 255, 255, 0.08)';
                        return (
                          <div key={st.key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div
                              style={{
                                height: 5,
                                borderRadius: 4,
                                background: barColor,
                                transition: 'background 0.25s ease',
                              }}
                            />
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: active ? 700 : 500,
                                color: reached ? 'var(--text-main)' : 'var(--text-dim)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 3,
                              }}
                            >
                              {reached && s.statut === 'RESOLU' && idx === 3 && (
                                <CheckCircle2 size={10} color="#10b981" />
                              )}
                              {st.label}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>
                      Signalement classé comme doublon / hors-périmètre.
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
