import React, { useState } from 'react';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Gauge,
} from 'lucide-react';
import {
  EvolutionTemporellePoint,
  SignalementStatistiques,
} from '../types';

interface MunicipalChartsProps {
  stats: SignalementStatistiques | null;
  activeCategorie?: string;
  onSelectCategorie?: (categorie: string) => void;
}

const CATEGORIE_META: Record<string, { label: string; color: string }> = {
  ACCIDENT: { label: 'Accidents', color: '#ef4444' },
  NID_DE_POULE: { label: 'Nids-de-poule', color: '#f59e0b' },
  ECLAIRAGE: { label: 'Éclairage', color: '#facc15' },
  DECHETS: { label: 'Déchets', color: '#10b981' },
  SIGNALISATION: { label: 'Signalisation', color: '#38bdf8' },
  AUTRE: { label: 'Autres', color: '#94a3b8' },
};

const GRAVITE_ORDER: Array<{ key: string; label: string; color: string }> = [
  { key: 'CRITIQUE', label: 'Critique', color: '#ef4444' },
  { key: 'ELEVEE', label: 'Élevée', color: '#f97316' },
  { key: 'MOYENNE', label: 'Moyenne', color: '#eab308' },
  { key: 'FAIBLE', label: 'Faible', color: '#38bdf8' },
];

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 18,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
  minWidth: 0,
};

const EMPTY_STATE_STYLE: React.CSSProperties = {
  height: 150,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 12.5,
  color: 'var(--text-dim)',
  border: '1px dashed var(--border-color)',
  borderRadius: 8,
  background: 'rgba(11, 17, 30, 0.45)',
};

function formatShortDate(isoDate: string): string {
  const parts = isoDate.split('-');
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}`;
}

export const MunicipalCharts: React.FC<MunicipalChartsProps> = ({
  stats,
  activeCategorie = 'TOUS',
  onSelectCategorie,
}) => {
  const [hoveredDay, setHoveredDay] = useState<EvolutionTemporellePoint | null>(null);

  const evolution = stats?.evolution_temporelle ?? [];
  const visibleEvolution = evolution.slice(-14);
  const maxDayTotal = Math.max(
    1,
    ...visibleEvolution.map((point) => point.total)
  );

  const parCategorieEntries = Object.entries(stats?.par_categorie ?? {}).sort(
    (a, b) => b[1] - a[1]
  );
  const totalCategorie = Math.max(
    1,
    parCategorieEntries.reduce((acc, [, val]) => acc + val, 0)
  );

  const totalSignalements = stats?.total_signalements ?? 0;
  const tauxResolution = Math.max(
    0,
    Math.min(100, stats?.taux_resolution_pourcent ?? 0)
  );
  const circleRadius = 35;
  const circleCircumference = 2 * Math.PI * circleRadius;
  const dashOffset =
    circleCircumference - (tauxResolution / 100) * circleCircumference;

  return (
    <section className="municipal-charts-grid">
      {/* 1. Évolution temporelle */}
      <div style={CARD_STYLE}>
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 10,
            marginBottom: 14,
            minHeight: 40,
          }}
        >
          <div>
            <h3
              style={{
                fontSize: 14,
                fontWeight: 700,
                color: 'var(--text-main)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                margin: 0,
              }}
            >
              <Activity size={16} color="#38bdf8" />
              <span>Évolution Temporelle</span>
            </h3>
            <p style={{ fontSize: 11.5, color: 'var(--text-muted)', margin: '3px 0 0' }}>
              Volumes journaliers (14 derniers jours actifs)
            </p>
          </div>

          {hoveredDay && (
            <div
              style={{
                textAlign: 'right',
                fontSize: 11,
                background: 'rgba(11, 17, 30, 0.95)',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                padding: '4px 8px',
                flexShrink: 0,
              }}
            >
              <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                {formatShortDate(hoveredDay.date)} · {hoveredDay.total} tot.
              </div>
              <div style={{ color: 'var(--text-muted)', marginTop: 1 }}>
                <span style={{ color: '#38bdf8' }}>{hoveredDay.en_attente}</span> att. ·{' '}
                <span style={{ color: '#f59e0b' }}>{hoveredDay.en_cours}</span> cours ·{' '}
                <span style={{ color: '#10b981' }}>{hoveredDay.resolus}</span> rés.
              </div>
            </div>
          )}
        </div>

        {visibleEvolution.length === 0 ? (
          <div style={EMPTY_STATE_STYLE}>
            Aucune donnée sur la période sélectionnée
          </div>
        ) : (
          <div>
            <div
              style={{
                height: 150,
                display: 'flex',
                alignItems: 'flex-end',
                gap: 6,
                padding: '10px 8px 0',
                borderBottom: '1px solid var(--border-color)',
                background: 'rgba(11, 17, 30, 0.5)',
                borderRadius: '8px 8px 0 0',
              }}
            >
              {visibleEvolution.map((day) => {
                const barHeightPct = Math.max(
                  10,
                  Math.round((day.total / maxDayTotal) * 100)
                );
                const resoluRatio =
                  day.total > 0 ? (day.resolus / day.total) * 100 : 0;
                const coursRatio =
                  day.total > 0 ? (day.en_cours / day.total) * 100 : 0;
                const attenteRatio = Math.max(
                  0,
                  100 - resoluRatio - coursRatio
                );

                return (
                  <div
                    key={day.date}
                    className="municipal-bar-col"
                    onMouseEnter={() => setHoveredDay(day)}
                    onMouseLeave={() => setHoveredDay(null)}
                    title={`${formatShortDate(day.date)} : ${day.total} total (${day.en_attente} att., ${day.en_cours} en cours, ${day.resolus} résolus)`}
                    style={{
                      flex: 1,
                      height: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'flex-end',
                      alignItems: 'center',
                      cursor: 'pointer',
                      minWidth: 10,
                    }}
                  >
                    <div
                      className="municipal-bar-inner"
                      style={{
                        width: '100%',
                        maxWidth: 24,
                        height: `${barHeightPct}%`,
                        borderRadius: '4px 4px 0 0',
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'flex-end',
                        background: 'rgba(30, 41, 59, 0.85)',
                        border: '1px solid rgba(51, 65, 85, 0.75)',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      {attenteRatio > 0 && (
                        <div
                          style={{
                            width: '100%',
                            height: `${attenteRatio}%`,
                            background: '#38bdf8',
                            flexShrink: 0,
                          }}
                        />
                      )}
                      {coursRatio > 0 && (
                        <div
                          style={{
                            width: '100%',
                            height: `${coursRatio}%`,
                            background: '#f59e0b',
                            flexShrink: 0,
                          }}
                        />
                      )}
                      {resoluRatio > 0 && (
                        <div
                          style={{
                            width: '100%',
                            height: `${resoluRatio}%`,
                            background: '#10b981',
                            flexShrink: 0,
                          }}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                flexWrap: 'wrap',
                fontSize: 11,
                color: 'var(--text-dim)',
                marginTop: 10,
                padding: '0 2px',
              }}
            >
              <span>{formatShortDate(visibleEvolution[0].date)}</span>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#38bdf8',
                      display: 'inline-block',
                    }}
                  />
                  Attente
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#f59e0b',
                      display: 'inline-block',
                    }}
                  />
                  En cours
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#10b981',
                      display: 'inline-block',
                    }}
                  />
                  Résolus
                </span>
              </div>

              <span>
                {formatShortDate(visibleEvolution[visibleEvolution.length - 1].date)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 2. Répartition par Catégorie */}
      <div style={CARD_STYLE}>
        <div style={{ marginBottom: 14 }}>
          <h3
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              margin: 0,
            }}
          >
            <BarChart3 size={16} color="#f59e0b" />
            <span>Répartition par Catégorie</span>
          </h3>
          <p style={{ fontSize: 11.5, color: 'var(--text-muted)', margin: '3px 0 0' }}>
            Cliquez sur une barre pour filtrer la file et la carte
          </p>
        </div>

        {parCategorieEntries.length === 0 ? (
          <div style={EMPTY_STATE_STYLE}>Aucune catégorie trouvée</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {parCategorieEntries.map(([catKey, count]) => {
              const meta = CATEGORIE_META[catKey] ?? {
                label: catKey,
                color: '#64748b',
              };
              const pct = Math.round((count / totalCategorie) * 100);
              const isSelected = activeCategorie === catKey;

              return (
                <button
                  key={catKey}
                  type="button"
                  className="municipal-cat-btn"
                  onClick={() =>
                    onSelectCategorie?.(isSelected ? 'TOUS' : catKey)
                  }
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    borderRadius: 8,
                    padding: '6px 8px',
                    cursor: 'pointer',
                    background: isSelected
                      ? 'rgba(56, 189, 248, 0.14)'
                      : 'rgba(11, 17, 30, 0.35)',
                    border: isSelected
                      ? '1px solid rgba(56, 189, 248, 0.45)'
                      : '1px solid transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: 12,
                      marginBottom: 5,
                    }}
                  >
                    <span style={{ color: '#e2e8f0', fontWeight: 500 }}>
                      {meta.label}
                    </span>
                    <span
                      style={{
                        color: 'var(--text-muted)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      <strong style={{ color: 'var(--text-main)' }}>{count}</strong> ({pct}%)
                    </span>
                  </div>
                  <div
                    style={{
                      height: 8,
                      width: '100%',
                      borderRadius: 999,
                      background: 'var(--bg-dark)',
                      border: '1px solid var(--border-color)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${Math.max(4, pct)}%`,
                        height: '100%',
                        borderRadius: 999,
                        background: meta.color,
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 3. Gravité & Taux de Résolution */}
      <div style={CARD_STYLE}>
        <div style={{ marginBottom: 14 }}>
          <h3
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              margin: 0,
            }}
          >
            <Gauge size={16} color="#10b981" />
            <span>Gravité &amp; Taux de Résolution</span>
          </h3>
          <p style={{ fontSize: 11.5, color: 'var(--text-muted)', margin: '3px 0 0' }}>
            Performance municipale sur les critères actifs
          </p>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
          }}
        >
          {/* Jauge SVG circulaire */}
          <div
            style={{
              position: 'relative',
              flexShrink: 0,
              width: 96,
              height: 96,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg
              width={96}
              height={96}
              viewBox="0 0 88 88"
              style={{ transform: 'rotate(-90deg)' }}
            >
              <circle
                cx="44"
                cy="44"
                r={circleRadius}
                fill="none"
                stroke="#1e293b"
                strokeWidth="8"
              />
              <circle
                cx="44"
                cy="44"
                r={circleRadius}
                fill="none"
                stroke="#10b981"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={circleCircumference}
                strokeDashoffset={dashOffset}
              />
            </svg>
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span
                style={{
                  fontSize: 17,
                  fontWeight: 800,
                  color: 'var(--text-main)',
                  fontVariantNumeric: 'tabular-nums',
                  lineHeight: 1.1,
                }}
              >
                {Math.round(tauxResolution)}%
              </span>
              <span
                style={{
                  fontSize: 10.5,
                  color: '#34d399',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 3,
                  marginTop: 2,
                }}
              >
                <CheckCircle2 size={10} />
                Résolus
              </span>
            </div>
          </div>

          {/* Barres gravité */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: 9,
              minWidth: 0,
            }}
          >
            {GRAVITE_ORDER.map(({ key, label, color }) => {
              const count = stats?.par_gravite?.[key] ?? 0;
              const pct =
                totalSignalements > 0
                  ? Math.round((count / totalSignalements) * 100)
                  : 0;
              return (
                <div key={key}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: 11.5,
                      marginBottom: 4,
                    }}
                  >
                    <span style={{ color: '#cbd5e1' }}>{label}</span>
                    <span
                      style={{
                        color: 'var(--text-muted)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      <strong style={{ color: 'var(--text-main)' }}>{count}</strong> ({pct}%)
                    </span>
                  </div>
                  <div
                    style={{
                      height: 6,
                      width: '100%',
                      borderRadius: 999,
                      background: 'var(--bg-dark)',
                      border: '1px solid var(--border-color)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${count > 0 ? Math.max(5, pct) : 0}%`,
                        height: '100%',
                        borderRadius: 999,
                        background: color,
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div
          style={{
            marginTop: 14,
            paddingTop: 10,
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
            fontSize: 11.5,
            color: 'var(--text-muted)',
          }}
        >
          <span>
            Chantiers voirie actifs :{' '}
            <strong style={{ color: '#fcd34d' }}>
              {stats?.details_chantiers?.voirie_active ?? 0}
            </strong>
          </span>
          <span>
            Zones critiques :{' '}
            <strong style={{ color: '#fda4af' }}>
              {
                (stats?.zones_haute_densite ?? []).filter(
                  (z) => z.nb_critiques_eleves > 0
                ).length
              }
            </strong>
          </span>
        </div>
      </div>
    </section>
  );
};
