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
  addStandardBasemapLayer,
  getGeoConfig,
  getRegionLeafletBounds,
  renderLocalityLabelsLayer,
} from '../config/geoConfig';
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

function getToolbarButtonStyle(
  active: boolean,
  activeColor: string,
  activeBg: string,
  activeBorder: string,
  disabled = false
): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 11px',
    borderRadius: 8,
    fontSize: 12,
    fontWeight: 600,
    border: `1px solid ${active ? activeBorder : 'var(--border-light)'}`,
    background: active ? activeBg : 'var(--bg-dark)',
    color: active ? activeColor : 'var(--text-muted)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
  };
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
      const radius = Math.max(16, Math.min(48, (zoom - 7.5) * 7.0));

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

    const geoCfg = getGeoConfig();
    const regionBounds = getRegionLeafletBounds(geoCfg);
    const map = L.map(container, {
      center: geoCfg.map.center,
      zoom: geoCfg.map.zoom,
      minZoom: geoCfg.map.min_zoom,
      maxZoom: geoCfg.map.max_zoom,
      maxBounds: regionBounds,
      maxBoundsViscosity: 1.0,
      attributionControl: false,
      zoomControl: true,
    });

    addStandardBasemapLayer(map);

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
    const labelsLayer = L.layerGroup().addTo(map);
    renderLocalityLabelsLayer(labelsLayer, geoCfg.delegations);
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
      map.fitBounds(regionBounds, { padding: [20, 20] });
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
        `${sig.quartier || getGeoConfig().default_city} · ${CATEGORIE_LABELS[sig.categorie] || sig.categorie} (${sig.statut})`,
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
        weight: 3,
        opacity: 0.85,
      });
      line.on('mouseover', () => line.setStyle({ weight: 4, opacity: 1 }));
      line.on('mouseout', () => line.setStyle({ weight: 3, opacity: 0.85 }));

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
        radius: Math.min(2000, Math.max(700, rz.rayon_zone_m || 1200)),
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
    <section
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: 12,
        overflow: 'hidden',
        marginBottom: 20,
      }}
    >
      <div
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
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
            <Flame size={16} color="#f59e0b" />
            <span>Carte de Chaleur &amp; Corrélation Régionale ({getGeoConfig().region_short_name})</span>
          </h3>
          <p
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              margin: '4px 0 0',
            }}
          >
            {heatmapPoints.length} points pondérés · {zonesHauteDensite.length} zone(s) dense(s)
            {activeAnomaliesCount > 0
              ? ` · ${activeAnomaliesCount} épicentre(s) anomalie IA`
              : ''}
          </p>
        </div>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <button
            type="button"
            className="municipal-heatmap-toolbar-btn"
            onClick={() => setShowHeatmap((v) => !v)}
            style={getToolbarButtonStyle(
              showHeatmap,
              '#fcd34d',
              'rgba(245, 158, 11, 0.18)',
              'rgba(245, 158, 11, 0.42)'
            )}
          >
            <Flame size={14} />
            <span>Heatmap</span>
          </button>

          <button
            type="button"
            className="municipal-heatmap-toolbar-btn"
            onClick={() => setShowClusters((v) => !v)}
            style={getToolbarButtonStyle(
              showClusters,
              '#7dd3fc',
              'rgba(56, 189, 248, 0.18)',
              'rgba(56, 189, 248, 0.42)'
            )}
          >
            <Layers size={14} />
            <span>Clusters ({zonesHauteDensite.length})</span>
          </button>

          <button
            type="button"
            className="municipal-heatmap-toolbar-btn"
            onClick={() => setShowMarkers((v) => !v)}
            style={getToolbarButtonStyle(
              showMarkers,
              '#a5b4fc',
              'rgba(99, 102, 241, 0.2)',
              'rgba(99, 102, 241, 0.45)'
            )}
          >
            <MapPin size={14} />
            <span>Points ({signalements.length})</span>
          </button>

          <button
            type="button"
            className="municipal-heatmap-toolbar-btn"
            onClick={() => setShowTraffic((v) => !v)}
            disabled={trafficSegments.length === 0}
            title={
              trafficSegments.length === 0
                ? 'Simulateur trafic (port 8001) indisponible'
                : 'Afficher les axes congestionnés (Module Trafic)'
            }
            style={getToolbarButtonStyle(
              showTraffic,
              '#6ee7b7',
              'rgba(16, 185, 129, 0.18)',
              'rgba(16, 185, 129, 0.42)',
              trafficSegments.length === 0
            )}
          >
            <Route size={14} />
            <span>Trafic Live ({trafficSegments.length})</span>
          </button>

          <button
            type="button"
            className="municipal-heatmap-toolbar-btn"
            onClick={() => setShowRiskMap((v) => !v)}
            disabled={riskZones.length === 0}
            title="Afficher les zones de risque routier IA (Protection Civile)"
            style={getToolbarButtonStyle(
              showRiskMap,
              '#fda4af',
              'rgba(244, 63, 94, 0.18)',
              'rgba(244, 63, 94, 0.42)',
              riskZones.length === 0
            )}
          >
            <ShieldAlert size={14} />
            <span>Risk Map IA ({riskZones.length})</span>
          </button>
        </div>
      </div>

      <div
        style={{
          position: 'relative',
          height: 390,
          width: '100%',
          background: 'var(--bg-darker)',
        }}
      >
        <div
          ref={containerRef}
          style={{ height: '100%', width: '100%', zIndex: 0 }}
        />

        {/* Légende compacte flottante */}
        <div
          style={{
            pointerEvents: 'none',
            position: 'absolute',
            bottom: 12,
            left: 12,
            zIndex: 450,
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 12,
            borderRadius: 8,
            border: '1px solid var(--border-light)',
            background: 'rgba(11, 17, 30, 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '7px 12px',
            fontSize: 11.5,
            color: '#cbd5e1',
          }}
        >
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <span
              style={{
                width: 56,
                height: 8,
                borderRadius: 999,
                display: 'inline-block',
                background:
                  'linear-gradient(90deg, #38bdf8, #10b981, #f59e0b, #ef4444)',
              }}
            />
            <span>Densité faible → critique</span>
          </span>
          {activeAnomaliesCount > 0 && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                color: '#fda4af',
              }}
            >
              <Sparkles size={12} />
              <span>Cercle pointillé : anomalie IA (cliquer pour filtrer)</span>
            </span>
          )}
        </div>
      </div>
    </section>
  );
};
