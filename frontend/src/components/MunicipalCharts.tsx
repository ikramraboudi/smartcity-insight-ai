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
  ACCIDENT: { label: 'Accidents', color: 'bg-rose-500' },
  NID_DE_POULE: { label: 'Nids-de-poule', color: 'bg-amber-500' },
  ECLAIRAGE: { label: 'Éclairage', color: 'bg-yellow-400' },
  DECHETS: { label: 'Déchets', color: 'bg-emerald-500' },
  SIGNALISATION: { label: 'Signalisation', color: 'bg-sky-500' },
  AUTRE: { label: 'Autres', color: 'bg-slate-400' },
};

const GRAVITE_ORDER: Array<{ key: string; label: string; color: string }> = [
  { key: 'CRITIQUE', label: 'Critique', color: 'bg-red-500' },
  { key: 'ELEVEE', label: 'Élevée', color: 'bg-orange-500' },
  { key: 'MOYENNE', label: 'Moyenne', color: 'bg-amber-400' },
  { key: 'FAIBLE', label: 'Faible', color: 'bg-sky-400' },
];

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
  const circleRadius = 36;
  const circleCircumference = 2 * Math.PI * circleRadius;
  const dashOffset =
    circleCircumference - (tauxResolution / 100) * circleCircumference;

  return (
    <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      {/* 1. Évolution temporelle */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 flex flex-col justify-between">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-sky-400" />
              Évolution Temporelle
            </h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Volumes journaliers par statut (14 derniers jours actifs)
            </p>
          </div>
          {hoveredDay && (
            <div className="text-right text-[11px] bg-slate-950/90 border border-slate-700 rounded-md px-2 py-1">
              <div className="font-semibold text-white">
                {formatShortDate(hoveredDay.date)} · {hoveredDay.total} tot.
              </div>
              <div className="text-slate-400">
                <span className="text-sky-400">{hoveredDay.en_attente}</span> att. ·{' '}
                <span className="text-amber-400">{hoveredDay.en_cours}</span> cours ·{' '}
                <span className="text-emerald-400">{hoveredDay.resolus}</span> rés.
              </div>
            </div>
          )}
        </div>

        {visibleEvolution.length === 0 ? (
          <div className="h-36 flex items-center justify-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
            Aucune donnée sur la période sélectionnée
          </div>
        ) : (
          <div>
            <div className="h-36 flex items-end gap-1.5 pt-2 pb-1 px-1 border-b border-slate-800">
              {visibleEvolution.map((day) => {
                const barHeightPct = Math.max(8, Math.round((day.total / maxDayTotal) * 100));
                const resoluRatio = day.total > 0 ? (day.resolus / day.total) * 100 : 0;
                const coursRatio = day.total > 0 ? (day.en_cours / day.total) * 100 : 0;
                const attenteRatio = Math.max(0, 100 - resoluRatio - coursRatio);

                return (
                  <div
                    key={day.date}
                    onMouseEnter={() => setHoveredDay(day)}
                    onMouseLeave={() => setHoveredDay(null)}
                    className="flex-1 h-full flex flex-col justify-end items-center group cursor-pointer"
                  >
                    <div
                      style={{ height: `${barHeightPct}%` }}
                      className="w-full max-w-[20px] rounded-t-sm overflow-hidden flex flex-col justify-end bg-slate-800/80 ring-1 ring-slate-700/60 group-hover:ring-sky-400 transition-all"
                    >
                      {attenteRatio > 0 && (
                        <div
                          style={{ height: `${attenteRatio}%` }}
                          className="w-full bg-sky-400/90"
                        />
                      )}
                      {coursRatio > 0 && (
                        <div
                          style={{ height: `${coursRatio}%` }}
                          className="w-full bg-amber-400/90"
                        />
                      )}
                      {resoluRatio > 0 && (
                        <div
                          style={{ height: `${resoluRatio}%` }}
                          className="w-full bg-emerald-400/90"
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1.5 px-1">
              <span>{formatShortDate(visibleEvolution[0].date)}</span>
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-sky-400" />
                  Attente
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  En cours
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
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
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 flex flex-col justify-between">
        <div className="mb-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-amber-400" />
            Répartition par Catégorie
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Cliquez sur une barre pour filtrer la file et la carte
          </p>
        </div>

        {parCategorieEntries.length === 0 ? (
          <div className="h-36 flex items-center justify-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
            Aucune catégorie trouvée
          </div>
        ) : (
          <div className="space-y-2.5">
            {parCategorieEntries.map(([catKey, count]) => {
              const meta = CATEGORIE_META[catKey] ?? {
                label: catKey,
                color: 'bg-slate-500',
              };
              const pct = Math.round((count / totalCategorie) * 100);
              const isSelected = activeCategorie === catKey;

              return (
                <button
                  key={catKey}
                  type="button"
                  onClick={() =>
                    onSelectCategorie?.(isSelected ? 'TOUS' : catKey)
                  }
                  className={`w-full text-left rounded-lg px-2 py-1 transition-colors ${
                    isSelected
                      ? 'bg-sky-500/15 ring-1 ring-sky-500/40'
                      : 'hover:bg-slate-800/70'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-slate-200 font-medium">{meta.label}</span>
                    <span className="text-slate-400 tabular-nums">
                      <strong className="text-white">{count}</strong> ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                    <div
                      style={{ width: `${Math.max(4, pct)}%` }}
                      className={`h-full rounded-full ${meta.color} transition-all duration-300`}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 3. Gravité & Taux de Résolution */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 flex flex-col justify-between">
        <div className="mb-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Gauge className="w-4 h-4 text-emerald-400" />
            Gravité & Taux de Résolution
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Performance municipale sur les critères actifs
          </p>
        </div>

        <div className="flex items-center gap-4">
          {/* Jauge SVG circulaire */}
          <div className="relative flex-shrink-0 w-24 h-24 flex items-center justify-center">
            <svg className="w-24 h-24 -rotate-90" viewBox="0 0 88 88">
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
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-base font-bold text-white tabular-nums">
                {Math.round(tauxResolution)}%
              </span>
              <span className="text-[10px] text-emerald-400 flex items-center gap-0.5">
                <CheckCircle2 className="w-2.5 h-2.5" />
                Résolus
              </span>
            </div>
          </div>

          {/* Barres gravité */}
          <div className="flex-1 space-y-2">
            {GRAVITE_ORDER.map(({ key, label, color }) => {
              const count = stats?.par_gravite?.[key] ?? 0;
              const pct =
                totalSignalements > 0
                  ? Math.round((count / totalSignalements) * 100)
                  : 0;
              return (
                <div key={key}>
                  <div className="flex items-center justify-between text-[11px] mb-0.5">
                    <span className="text-slate-300">{label}</span>
                    <span className="text-slate-400 tabular-nums">
                      <strong className="text-white">{count}</strong> ({pct}%)
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                    <div
                      style={{ width: `${count > 0 ? Math.max(5, pct) : 0}%` }}
                      className={`h-full rounded-full ${color}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span>
            Chantiers voirie actifs :{' '}
            <strong className="text-amber-300">
              {stats?.details_chantiers?.voirie_active ?? 0}
            </strong>
          </span>
          <span>
            Zones critiques :{' '}
            <strong className="text-rose-300">
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
