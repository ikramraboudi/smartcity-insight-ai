import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import {
  Flame,
  Layers,
  MapPin,
  Route,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import {
  AlerteAnomalieItem,
  Signalement,
  TrafficSegment,
  ZoneHauteDensite,
  ZoneRiskMap,
} from '../types';

interface MunicipalHeatmapProps {
  heatmapPoints: [number, number, number][];
  zonesHauteDensite: ZoneHauteDensite[];
  signalements: Signalement[];
  anomalies: AlerteAnomalieItem[];
  trafficSegments: TrafficSegment[];
  riskZones: ZoneRiskMap[];
  onFilterZone?: (quartier: string, categorie?: string) => void;
  onSelectSignalement?: (sig: Signalement) => void;
}

const GRAND_TUNIS_CENTER: [number, number] = [36.8123, 10.1784];
const GRAND_TUNIS_BOUNDS: [[number, number], [number, number]] = [
  [36.45, 9.85],
  [37.18, 10.58],
];

const CATEGORIE_LABELS: Record<string, string> = {
  ACCIDENT: 'Accident / Urgence',
  NID_DE_POULE: 'Nid-de-poule & Voirie',
  ECLAIRAGE: 'Éclairage public',
  DECHETS: 'Déchets & Propreté',
  SIGNALISATION: 'Signalisation / Feux',
  AUTRE: 'Autre',
};

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildThermalPalette(): Uint8ClampedArray {
  const paletteCanvas = document.createElement('canvas');
  paletteCanvas.width = 256;
  paletteCanvas.height = 1;
  const ctx = paletteCanvas.getContext('2d');
  if (!ctx) return new Uint8ClampedArray(256 * 4);

  const grad = ctx.createLinearGradient(0, 0, 256, 0);
  grad.addColorStop(0.0, 'rgba(56, 189, 248, 0)');
  grad.addColorStop(0.25, 'rgba(56, 189, 248, 1)');
  grad.addColorStop(0.5, 'rgba(16, 185, 129, 1)');
  grad.addColorStop(0.75, 'rgba(245, 158, 11, 1)');
  grad.addColorStop(1.0, 'rgba(239, 68, 68, 1)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 256, 1);

  return ctx.getImageData(0, 0, 256, 1).data;
}

export const MunicipalHeatmap: React.FC<MunicipalHeatmapProps> = ({
  heatmapPoints,
  zonesHauteDensite,
  signalements,
  anomalies,
  trafficSegments,
  riskZones,
  onFilterZone,
  onSelectSignalement,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const paletteRef = useRef<Uint8ClampedArray | null>(null);

  const hotspotsLayerRef = useRef<L.LayerGroup | null>(null);
  const anomaliesLayerRef = useRef<L.LayerGroup | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const trafficLayerRef = useRef<L.LayerGroup | null>(null);
  const riskLayerRef = useRef<L.LayerGroup | null>(null);

  const heatmapPointsRef = useRef(heatmapPoints);
  const showHeatmapRef = useRef(true);
  const onFilterZoneRef = useRef(onFilterZone);
  const onSelectSignalementRef = useRef(onSelectSignalement);

  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showClusters, setShowClusters] = useState(true);
  const [showMarkers, setShowMarkers] = useState(false);
  const [showTraffic, setShowTraffic] = useState(false);
  const [showRiskMap, setShowRiskMap] = useState(false);

  useEffect(() => {
    heatmapPointsRef.current = heatmapPoints;
    showHeatmapRef.current = showHeatmap;
    onFilterZoneRef.current = onFilterZone;
    onSelectSignalementRef.current = onSelectSignalement;
  }, [heatmapPoints, showHeatmap, onFilterZone, onSelectSignalement]);

  // Helper impératif de rendu thermique sur le canvas overlay Leaflet
  const redrawCanvasRef = useRef<() => void>(() => {});

  useEffect(() => {
    const redraw = () => {
      const map = mapRef.current;
      const canvas = canvasRef.current;
      if (!map || !canvas) return;

      const size = map.getSize();
      if (size.x <= 0 || size.y <= 0) return;

      if (canvas.width !== size.x || canvas.height !== size.y) {
        canvas.width = size.x;
        canvas.height = size.y;
      }

      const topLeft = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(canvas, topLeft);

      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      if (!ctx) return;

      ctx.clearRect(0, 0, size.x, size.y);

      const points = heatmapPointsRef.current;
      if (!showHeatmapRef.current || points.length === 0) {
        return;
      }

      if (!paletteRef.current) {
        paletteRef.current = buildThermalPalette();
      }
      const palette = paletteRef.current;

      const zoom = map.getZoom();
      const radius = Math.max(20, Math.min(48, (zoom - 8) * 7.5));

      for (let i = 0; i < points.length; i += 1) {
        const [lat, lng, weight] = points[i];
        const pt = map.latLngToContainerPoint([lat, lng]);
        if (
          pt.x < -radius ||
          pt.y < -radius ||
          pt.x > size.x + radius ||
          pt.y > size.y + radius
        ) {
          continue;
        }

        const alpha = Math.max(0.18, Math.min(0.85, (weight || 0.5) * 0.65));
        const rad = ctx.createRadialGradient(pt.x, pt.y, 1, pt.x, pt.y, radius);
        rad.addColorStop(0, `rgba(0, 0, 0, ${alpha})`);
        rad.addColorStop(0.55, `rgba(0, 0, 0, ${alpha * 0.45})`);
        rad.addColorStop(1, 'rgba(0, 0, 0, 0)');

        ctx.fillStyle = rad;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2);
        ctx.fill();
      }

      const img = ctx.getImageData(0, 0, size.x, size.y);
      const data = img.data;
      for (let i = 0; i < data.length; i += 4) {
        const rawAlpha = data[i + 3];
        if (rawAlpha > 6) {
          const idx = rawAlpha * 4;
          data[i] = palette[idx];
          data[i + 1] = palette[idx + 1];
          data[i + 2] = palette[idx + 2];
          data[i + 3] = Math.min(205, Math.round(rawAlpha * 0.92));
        }
      }
      ctx.putImageData(img, 0, 0);
    };

    redrawCanvasRef.current = redraw;
  });

  // Initialisation unique de la carte Leaflet
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, {
      center: GRAND_TUNIS_CENTER,
      zoom: 12,
      minZoom: 10,
      maxZoom: 18,
      maxBounds: GRAND_TUNIS_BOUNDS,
      maxBoundsViscosity: 0.85,
      attributionControl: false,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    const heatmapPane = map.createPane('heatmapPane');
    heatmapPane.style.zIndex = '410';
    heatmapPane.style.pointerEvents = 'none';

    const canvas = document.createElement('canvas');
    canvas.className = 'leaflet-heatmap-layer';
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.pointerEvents = 'none';
    heatmapPane.appendChild(canvas);

    mapRef.current = map;
    canvasRef.current = canvas;

    trafficLayerRef.current = L.layerGroup().addTo(map);
    riskLayerRef.current = L.layerGroup().addTo(map);
    hotspotsLayerRef.current = L.layerGroup().addTo(map);
    markersLayerRef.current = L.layerGroup().addTo(map);
    anomaliesLayerRef.current = L.layerGroup().addTo(map);

    const triggerRedraw = () => {
      window.requestAnimationFrame(() => {
        redrawCanvasRef.current();
      });
    };

    map.on('moveend zoomend viewreset resize', triggerRedraw);

    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
      triggerRedraw();
    });
    resizeObserver.observe(container);

    window.setTimeout(() => {
      map.invalidateSize({ animate: false });
      triggerRedraw();
    }, 120);

    return () => {
      resizeObserver.disconnect();
      map.off('moveend zoomend viewreset resize', triggerRedraw);
      map.remove();
      mapRef.current = null;
      canvasRef.current = null;
      trafficLayerRef.current = null;
      riskLayerRef.current = null;
      hotspotsLayerRef.current = null;
      markersLayerRef.current = null;
      anomaliesLayerRef.current = null;
    };
  }, []);

  // Redessiner la couche thermique lorsque les points ou le toggle changent
  useEffect(() => {
    window.requestAnimationFrame(() => {
      redrawCanvasRef.current();
    });
  }, [heatmapPoints, showHeatmap]);

  // Couche Zones Haute Densité (Clusters)
  useEffect(() => {
    const layer = hotspotsLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showClusters) return;

    zonesHauteDensite.forEach((zone) => {
      const radius = Math.max(9, Math.min(26, 7 + zone.nb_signalements * 2.1));
      const hasCritical = zone.nb_critiques_eleves > 0;
      const strokeColor = hasCritical ? '#f59e0b' : '#38bdf8';
      const fillColor = hasCritical ? '#ef4444' : '#0ea5e9';

      const circle = L.circleMarker([zone.latitude, zone.longitude], {
        radius,
        color: strokeColor,
        weight: 2,
        opacity: 0.9,
        fillColor,
        fillOpacity: 0.28,
      });

      const catLabel =
        CATEGORIE_LABELS[zone.categorie_dominante] || zone.categorie_dominante;

      circle.bindPopup(`
        <div style="min-width:190px;font-family:system-ui,sans-serif;color:#0f172a">
          <div style="font-weight:700;font-size:13px;margin-bottom:4px">${escapeHtml(zone.zone)}</div>
          <div style="font-size:12px;line-height:1.5">
            <b>${zone.nb_signalements}</b> signalement(s) (${zone.nb_actifs} actifs)<br/>
            Critiques / Élevés : <b>${zone.nb_critiques_eleves}</b><br/>
            Dominante : <b>${escapeHtml(catLabel)}</b><br/>
            Score densité : <b>${zone.score_densite}</b>
          </div>
        </div>
      `);

      circle.on('click', () => {
        onFilterZoneRef.current?.(zone.zone);
      });

      circle.addTo(layer);
    });
  }, [zonesHauteDensite, showClusters]);

  // Couche Épicentres Anomalies Isolation Forest
  useEffect(() => {
    const layer = anomaliesLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    anomalies
      .filter(
        (item) =>
          item.statut === 'ACTIVE' &&
          item.latitude_centre !== null &&
          item.longitude_centre !== null
      )
      .forEach((item) => {
        const lat = item.latitude_centre as number;
        const lng = item.longitude_centre as number;
        const color =
          item.severite === 'CRITIQUE'
            ? '#ef4444'
            : item.severite === 'ELEVEE'
              ? '#f97316'
              : '#eab308';

        const halo = L.circle([lat, lng], {
          radius: 420,
          color,
          weight: 2,
          dashArray: '6 4',
          fillColor: color,
          fillOpacity: 0.14,
        });

        const core = L.circleMarker([lat, lng], {
          radius: 7,
          color: '#ffffff',
          weight: 2,
          fillColor: color,
          fillOpacity: 1,
        });

        const scoreDisplay =
          item.score_anomalie <= 1
            ? Math.round(item.score_anomalie * 100)
            : Math.round(item.score_anomalie);
        const catLabel = CATEGORIE_LABELS[item.categorie] || item.categorie;
        const popupHtml = `
          <div style="min-width:210px;font-family:system-ui,sans-serif;color:#0f172a">
            <div style="font-weight:700;font-size:13px;color:#b91c1c;margin-bottom:4px">
              Anomalie IA (${scoreDisplay}%)
            </div>
            <div style="font-size:12px;line-height:1.45">
              <b>${escapeHtml(item.quartier)}</b> — ${escapeHtml(catLabel)}<br/>
              ${item.nb_signalements} signalements / ${item.fenetre_heures}h<br/>
              <span style="color:#475569">${escapeHtml(item.explication)}</span>
            </div>
          </div>
        `;

        halo.bindPopup(popupHtml);
        core.bindPopup(popupHtml);

        const handleSelect = () => {
          onFilterZoneRef.current?.(item.quartier, item.categorie);
        };
        halo.on('click', handleSelect);
        core.on('click', handleSelect);

        halo.addTo(layer);
        core.addTo(layer);
      });
  }, [anomalies]);

  // Couche Signalements Individuels (optionnelle)
  useEffect(() => {
    const layer = markersLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showMarkers) return;

    signalements.slice(0, 150).forEach((sig) => {
      const color =
        sig.gravite === 'CRITIQUE'
          ? '#ef4444'
          : sig.gravite === 'ELEVEE'
            ? '#f97316'
            : sig.gravite === 'MOYENNE'
              ? '#eab308'
              : '#38bdf8';

      const marker = L.circleMarker([sig.latitude, sig.longitude], {
        radius: 5,
        color: '#0f172a',
        weight: 1.5,
        fillColor: color,
        fillOpacity: 0.92,
      });

      marker.bindTooltip(
        `${sig.quartier || 'Tunis'} · ${CATEGORIE_LABELS[sig.categorie] || sig.categorie} (${sig.statut})`,
        { direction: 'top' }
      );

      marker.on('click', () => {
        onSelectSignalementRef.current?.(sig);
      });

      marker.addTo(layer);
    });
  }, [signalements, showMarkers]);

  // Overlay Trafic ML (Étudiant 1)
  useEffect(() => {
    const layer = trafficLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showTraffic || trafficSegments.length === 0) return;

    trafficSegments.forEach((seg) => {
      if (!seg.coordinates || seg.coordinates.length < 2) return;
      const line = L.polyline(seg.coordinates, {
        color: seg.color || '#38bdf8',
        weight: seg.congestion_level === 'BLOCKED' || seg.congestion_level === 'HEAVY' ? 5 : 3.5,
        opacity: 0.85,
      });

      line.bindTooltip(
        `${seg.name} (${seg.zone}) · ${seg.current_speed_kmh} km/h · Indice ${(seg.congestion_index * 100).toFixed(0)}%`,
        { sticky: true }
      );
      line.addTo(layer);
    });
  }, [trafficSegments, showTraffic]);

  // Overlay Risk Map IA (Étudiant 3)
  useEffect(() => {
    const layer = riskLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showRiskMap || riskZones.length === 0) return;

    riskZones.forEach((rz) => {
      const color =
        rz.niveau_couleur === 'rouge'
          ? '#ef4444'
          : rz.niveau_couleur === 'orange'
            ? '#f59e0b'
            : '#10b981';

      const circle = L.circle([rz.latitude, rz.longitude], {
        radius: 650,
        color,
        weight: 1.5,
        fillColor: color,
        fillOpacity: rz.niveau_couleur === 'rouge' ? 0.22 : 0.14,
      });

      circle.bindPopup(`
        <div style="min-width:190px;font-family:system-ui,sans-serif;color:#0f172a">
          <div style="font-weight:700;font-size:13px">${escapeHtml(rz.zone_nom)}</div>
          <div style="font-size:12px;margin-top:4px">
            Risk Map IA : <b>${rz.score_risque_pourcentage}%</b> (${escapeHtml(rz.niveau_risk_map)})<br/>
            <span style="color:#475569">${escapeHtml((rz.facteurs_explicatifs || []).slice(0, 2).join(' · '))}</span>
          </div>
        </div>
      `);
      circle.addTo(layer);
    });
  }, [riskZones, showRiskMap]);

  const activeAnomaliesCount = anomalies.filter((a) => a.statut === 'ACTIVE').length;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden mb-6">
      <div className="px-4 py-3 border-b border-slate-800 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Flame className="w-4 h-4 text-amber-400" />
            Carte de Chaleur & Corrélation Urbaine (Grand Tunis)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {heatmapPoints.length} points pondérés · {zonesHauteDensite.length} zone(s) dense(s)
            {activeAnomaliesCount > 0
              ? ` · ${activeAnomaliesCount} épicentre(s) anomalie IA`
              : ''}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setShowHeatmap((v) => !v)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors ${
              showHeatmap
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            Heatmap
          </button>

          <button
            type="button"
            onClick={() => setShowClusters((v) => !v)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors ${
              showClusters
                ? 'bg-sky-500/20 border-sky-500/40 text-sky-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Clusters ({zonesHauteDensite.length})
          </button>

          <button
            type="button"
            onClick={() => setShowMarkers((v) => !v)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors ${
              showMarkers
                ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <MapPin className="w-3.5 h-3.5" />
            Points ({signalements.length})
          </button>

          <button
            type="button"
            onClick={() => setShowTraffic((v) => !v)}
            disabled={trafficSegments.length === 0}
            title={
              trafficSegments.length === 0
                ? 'Simulateur trafic (port 8001) indisponible'
                : 'Afficher les axes congestionnés (Module Trafic)'
            }
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors disabled:opacity-45 disabled:cursor-not-allowed ${
              showTraffic
                ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <Route className="w-3.5 h-3.5" />
            Trafic Live ({trafficSegments.length})
          </button>

          <button
            type="button"
            onClick={() => setShowRiskMap((v) => !v)}
            disabled={riskZones.length === 0}
            title="Afficher les zones de risque routier IA (Protection Civile)"
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors disabled:opacity-45 disabled:cursor-not-allowed ${
              showRiskMap
                ? 'bg-rose-500/20 border-rose-500/40 text-rose-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            Risk Map IA ({riskZones.length})
          </button>
        </div>
      </div>

      <div className="relative h-[380px] w-full bg-slate-950">
        <div ref={containerRef} className="h-full w-full z-0" />

        {/* Légende compacte flottante */}
        <div className="pointer-events-none absolute bottom-3 left-3 z-[450] flex flex-wrap items-center gap-3 rounded-lg border border-slate-700/80 bg-slate-950/90 px-3 py-2 text-[11px] text-slate-300 backdrop-blur">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-12 rounded-full bg-gradient-to-r from-sky-400 via-emerald-400 via-amber-400 to-red-500" />
            Densité faible → critique
          </span>
          {activeAnomaliesCount > 0 && (
            <span className="inline-flex items-center gap-1 text-rose-300">
              <Sparkles className="w-3 h-3" />
              Cercle pointillé : anomalie IA (cliquer pour filtrer)
            </span>
          )}
        </div>
      </div>
    </section>
  );
};
