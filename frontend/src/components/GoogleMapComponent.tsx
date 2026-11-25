import React, { useEffect, useRef, useCallback, useState } from 'react';
import L from 'leaflet';
import type { Alerte, Caserne, RouteInfo, ZoneRiskMap } from '../types';
import {
  addStandardBasemapLayer,
  FALLBACK_CASERNES_CAP_BON,
  getGeoConfig,
  getRegionLeafletBounds,
  renderLocalityLabelsLayer,
} from '../config/geoConfig';
import {
  fetchTrafficSegments,
  calculateSimulatorRouteDelay,
  fetchZonesRiskMap,
} from '../services/api';

interface GoogleMapComponentProps {
  casernes: Caserne[];
  alertes: Alerte[];
  selectedAlerte: Alerte | null;
  selectedCaserne: Caserne | null;
  trafficLayerActive: boolean;
  onSelectAlerte: (alerte: Alerte) => void;
  onRouteCalculated: (route: RouteInfo | null) => void;
}

export const GoogleMapComponent: React.FC<GoogleMapComponentProps> = ({
  casernes,
  alertes,
  selectedAlerte,
  selectedCaserne,
  trafficLayerActive,
  onSelectAlerte,
  onRouteCalculated,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);

  // État d'affichage de la couche Risk Map
  const [riskMapLayerActive, setRiskMapLayerActive] = useState<boolean>(true);
  const [zonesRisk, setZonesRisk] = useState<ZoneRiskMap[]>([]);

  // Leaflet map instances
  const leafletMapRef = useRef<L.Map | null>(null);
  const leafletLabelsLayerRef = useRef<L.LayerGroup | null>(null);
  const leafletMarkersRef = useRef<L.LayerGroup | null>(null);
  const leafletTrafficLayerRef = useRef<L.LayerGroup | null>(null);
  const leafletRiskLayerRef = useRef<L.LayerGroup | null>(null);
  const leafletRouteLayerRef = useRef<L.Polyline | null>(null);
  const selectedAlerteRef = useRef<Alerte | null>(selectedAlerte);

  useEffect(() => {
    selectedAlerteRef.current = selectedAlerte;
  }, [selectedAlerte]);


  // Distance Haversine helper
  const calculateDistanceKm = (lat1: number, lon1: number, lat2: number, lon2: number) => {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  };

  // Trouver la caserne la plus proche
  const getNearestCaserne = useCallback(
    (alerte: Alerte): Caserne => {
      if (selectedCaserne) return selectedCaserne;
      if (casernes.length === 0) {
        return FALLBACK_CASERNES_CAP_BON[0];
      }
      let nearest = casernes[0];
      let minDis = calculateDistanceKm(alerte.latitude, alerte.longitude, nearest.latitude, nearest.longitude);
      for (let i = 1; i < casernes.length; i++) {
        const d = calculateDistanceKm(alerte.latitude, alerte.longitude, casernes[i].latitude, casernes[i].longitude);
        if (d < minDis) {
          minDis = d;
          nearest = casernes[i];
        }
      }
      return nearest;
    },
    [casernes, selectedCaserne]
  );

  // 1. Initialiser la carte Leaflet sur le Nord-Est du Cap Bon avec cadrage optimal
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (leafletMapRef.current) return;

    const geoCfg = getGeoConfig();
    const regionBounds = getRegionLeafletBounds(geoCfg);

    const map = L.map(mapContainerRef.current, {
      center: geoCfg.map.center,
      zoom: geoCfg.map.zoom,
      minZoom: geoCfg.map.min_zoom,
      maxZoom: geoCfg.map.max_zoom,
      maxBounds: regionBounds,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    // Repositionner le contrôle de zoom en haut à gauche
    L.control.zoom({ position: 'topleft' }).addTo(map);

    // Couche OpenStreetMap standard (sans filtre CSS)
    addStandardBasemapLayer(map);

    leafletTrafficLayerRef.current = L.layerGroup().addTo(map);
    leafletRiskLayerRef.current = L.layerGroup().addTo(map);
    leafletLabelsLayerRef.current = L.layerGroup().addTo(map);
    leafletMarkersRef.current = L.layerGroup().addTo(map);
    leafletMapRef.current = map;

    renderLocalityLabelsLayer(leafletLabelsLayerRef.current, geoCfg.delegations);

    const fitWorkingZone = () => {
      if (!mapContainerRef.current) return;
      map.invalidateSize();
      map.fitBounds(regionBounds, { padding: [20, 20] });
    };

    fitWorkingZone();
    const t1 = setTimeout(() => {
      if (!selectedAlerteRef.current) {
        fitWorkingZone();
      } else {
        map.invalidateSize();
      }
    }, 100);
    const t2 = setTimeout(() => {
      map.invalidateSize();
    }, 350);

    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });
    resizeObserver.observe(mapContainerRef.current);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      resizeObserver.disconnect();
      if (leafletLabelsLayerRef.current) {
        leafletLabelsLayerRef.current.clearLayers();
        leafletLabelsLayerRef.current = null;
      }
      if (leafletRiskLayerRef.current) {
        leafletRiskLayerRef.current.clearLayers();
        leafletRiskLayerRef.current = null;
      }
      if (leafletTrafficLayerRef.current) {
        leafletTrafficLayerRef.current.clearLayers();
        leafletTrafficLayerRef.current = null;
      }
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
  }, []);


  // 2. Mise à jour des marqueurs (Casernes 🚒 et Accidents 🚨)
  useEffect(() => {
    if (!leafletMapRef.current || !leafletMarkersRef.current) return;

    leafletMarkersRef.current.clearLayers();

    // Marqueurs Casernes (🚒)
    casernes.forEach((c) => {
      const fireIcon = L.divIcon({
        className: 'custom-fire-marker',
        html: '🚒',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });

      const m = L.marker([c.latitude, c.longitude], { icon: fireIcon });
      m.bindPopup(`
        <div style="color: #0f172a; font-family: sans-serif; font-size: 12px; min-width: 190px;">
          <strong style="color: #0284c7; font-size: 13px;">🚒 ${c.nom}</strong><br/>
          <span style="color: #64748b; font-size: 11px;">📍 ${c.adresse}</span>
          <div style="margin-top: 6px; padding: 4px 6px; background: #e0f2fe; border-radius: 4px; color: #0369a1; font-weight: bold; font-size: 11px;">
            🚑 ${c.ambulances_disponibles} ambulances • 🚒 ${c.camions_disponibles} camions
          </div>
          <div style="margin-top: 4px; font-size: 11px; color: #334155;">
            📞 Urgences : <strong>${c.telephone}</strong>
          </div>
        </div>
      `);
      m.addTo(leafletMarkersRef.current!);
    });

    // Marqueurs Accidents UNIQUEMENT pour les alertes actives (les interventions clôturées disparaissent de la carte)
    const alertesActives = alertes.filter((a) => a.statut !== 'CLOTURE');

    alertesActives.forEach((a) => {
      let cls = 'custom-accident-marker';
      if (a.gravite === 'GRAVE') cls += ' grave';
      else if (a.gravite === 'MOYENNE') cls += ' moyenne';
      else cls += ' faible';
      if (a.statut === 'PRISE_EN_CHARGE') cls += ' resolu';

      const accidentIcon = L.divIcon({
        className: cls,
        html: '🚨',
        iconSize: [30, 30],
        iconAnchor: [15, 15],
      });

      const m = L.marker([a.latitude, a.longitude], { icon: accidentIcon });
      m.bindPopup(`
        <div style="color: #0f172a; font-family: sans-serif; font-size: 12px; min-width: 180px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: #dc2626; font-size: 13px;">🚨 ACCIDENT #${a.id}</strong>
            <span style="background: #fee2e2; color: #dc2626; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">
              ${a.gravite}
            </span>
          </div>
          <span style="color: #334155;">📍 ${a.adresse}</span><br/>
          <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
            👥 ${a.nb_signalements} signalements confirmés
          </div>
          <div style="margin-top: 4px; font-size: 11px; color: #0284c7; font-weight: bold;">
            Statut : ${a.statut}
          </div>
        </div>
      `);
      m.on('click', () => onSelectAlerte(a));
      m.addTo(leafletMarkersRef.current!);
    });
  }, [casernes, alertes, onSelectAlerte]);

  // 3. Affichage de la couche de trafic simulé en temps réel (Cap Bon)
  useEffect(() => {
    if (!leafletMapRef.current) return;
    if (!leafletTrafficLayerRef.current) {
      leafletTrafficLayerRef.current = L.layerGroup().addTo(leafletMapRef.current);
    }

    if (!trafficLayerActive) {
      leafletTrafficLayerRef.current.clearLayers();
      return;
    }

    let isMounted = true;
    const updateTrafficPolylines = async () => {
      const segments = await fetchTrafficSegments();
      if (!isMounted || !leafletTrafficLayerRef.current) return;

      leafletTrafficLayerRef.current.clearLayers();

      segments.forEach((seg) => {
        const poly = L.polyline(seg.coordinates as [number, number][], {
          color: seg.color,
          weight: 3,
          opacity: 0.85,
          lineCap: 'round',
          lineJoin: 'round',
        });

        poly.on('mouseover', () => {
          poly.setStyle({ weight: 4, opacity: 1 });
        });
        poly.on('mouseout', () => {
          poly.setStyle({ weight: 3, opacity: 0.85 });
        });

        poly.bindPopup(`
          <div style="color: #0f172a; font-family: sans-serif; font-size: 12px; min-width: 210px;">
            <strong style="color: #0284c7; font-size: 13px;">🚦 ${seg.name}</strong><br/>
            <span style="color: #64748b; font-size: 11px;">Zone : ${seg.zone}</span>
            <div style="margin-top: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span>Vitesse en direct :</span>
              <strong style="color: ${seg.color}; font-size: 13px;">${seg.current_speed_kmh} km/h</strong>
            </div>
            <div style="font-size: 11px; color: #64748b;">Vitesse max autorisée : ${seg.base_speed_kmh} km/h</div>
            <div style="margin-top: 6px; padding: 4px 6px; background: #f1f5f9; border-radius: 4px; font-weight: bold; font-size: 11px; color: #334155;">
              Congestion : <span style="color: ${seg.color};">${seg.congestion_level}</span> (Indice ${seg.congestion_index}/5)
            </div>
            ${
              seg.has_incident
                ? `<div style="margin-top: 4px; color: #dc2626; font-weight: bold; font-size: 11px;">⚠️ ${seg.incident_description || 'Incident en cours'}</div>`
                : ''
            }
          </div>
        `);

        poly.addTo(leafletTrafficLayerRef.current!);
      });
    };

    updateTrafficPolylines();
    const interval = setInterval(updateTrafficPolylines, 4000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [trafficLayerActive]);

  // 3bis. Affichage de la couche Risk Map (Secteurs colorés vert/orange/rouge & facteurs)
  useEffect(() => {
    let isMounted = true;
    fetchZonesRiskMap().then((data) => {
      if (isMounted) setZonesRisk(data);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!leafletMapRef.current) return;
    if (!leafletRiskLayerRef.current) {
      leafletRiskLayerRef.current = L.layerGroup().addTo(leafletMapRef.current);
    }

    leafletRiskLayerRef.current.clearLayers();
    if (!riskMapLayerActive) return;

    zonesRisk.forEach((z) => {
      const color =
        z.niveau_couleur === 'rouge'
          ? '#ef4444'
          : z.niveau_couleur === 'orange'
          ? '#f59e0b'
          : '#10b981';

      const circle = L.circle([z.latitude, z.longitude], {
        radius: Math.min(1800, Math.max(550, z.rayon_zone_m || 1100)),
        color: color,
        fillColor: color,
        fillOpacity: 0.22,
        weight: 2,
        dashArray: '5, 5',
      });

      const facteursHtml = (z.facteurs_explicatifs || [])
        .map((f) => `<li>${f}</li>`)
        .join('');

      circle.bindPopup(`
        <div style="color: #0f172a; font-family: sans-serif; font-size: 12px; min-width: 210px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: ${color}; font-size: 13px;">🛡️ ${z.zone_nom}</strong>
            <span style="background: ${color}22; color: ${color}; padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: bold;">
              ${z.score_risque_pourcentage}%
            </span>
          </div>
          <span style="color: #64748b; font-size: 11px;">Tronçon : ${z.type_troncon || 'Zone urbaine'}</span>
          <div style="margin-top: 6px; padding: 4px 6px; background: #f8fafc; border-radius: 4px; border: 1px solid #e2e8f0;">
            <strong style="font-size: 10.5px; color: #334155;">Facteurs explicatifs :</strong>
            <ul style="margin: 2px 0 0 0; padding-left: 14px; font-size: 10.5px; color: #475569;">
              ${facteursHtml}
            </ul>
          </div>
        </div>
      `);

      circle.addTo(leafletRiskLayerRef.current!);
    });
  }, [zonesRisk, riskMapLayerActive]);

  // 4. Calcul de l'itinéraire le plus rapide et tracé sur la carte

  useEffect(() => {
    if (!leafletMapRef.current) return;

    // Si aucune alerte sélectionnée ou si l'alerte est CLÔTURÉE, effacer le tracé d'itinéraire
    if (!selectedAlerte || selectedAlerte.statut === 'CLOTURE') {
      if (leafletRouteLayerRef.current) {
        leafletMapRef.current.removeLayer(leafletRouteLayerRef.current);
        leafletRouteLayerRef.current = null;
      }
      onRouteCalculated(null);
      return;
    }

    const caserne = getNearestCaserne(selectedAlerte);
    const dis = calculateDistanceKm(
      caserne.latitude,
      caserne.longitude,
      selectedAlerte.latitude,
      selectedAlerte.longitude
    );

    // Points de passage de l'itinéraire
    const latMid = (caserne.latitude + selectedAlerte.latitude) / 2 + 0.0015;
    const lngMid = (caserne.longitude + selectedAlerte.longitude) / 2 - 0.002;
    const polyCoordinates: [number, number][] = [
      [caserne.latitude, caserne.longitude],
      [latMid, lngMid],
      [selectedAlerte.latitude, selectedAlerte.longitude],
    ];

    if (leafletRouteLayerRef.current) {
      leafletMapRef.current.removeLayer(leafletRouteLayerRef.current);
    }

    leafletRouteLayerRef.current = L.polyline(polyCoordinates, {
      color: '#ef4444',
      weight: 6,
      opacity: 0.9,
      dashArray: '10, 6',
    }).addTo(leafletMapRef.current);

    // Recadrer avec zoom intelligent sécurisé (ne dézoome jamais au monde)
    const bounds = L.latLngBounds(polyCoordinates);
    leafletMapRef.current.fitBounds(bounds, {
      padding: [60, 60],
      maxZoom: 15,
    });

    let isCancelled = false;

    const computeAndNotifyRoute = async () => {
      const avgSpeedKmh = dis > 8 ? 65 : 45;
      let rawDuration = Math.round((dis / avgSpeedKmh) * 60) + 1;
      let durationWithTraffic = rawDuration + (trafficLayerActive ? 2 : 0);
      let trafficDelay = trafficLayerActive ? 2 : 0;
      let warningMsg: string | undefined = undefined;

      if (trafficLayerActive) {
        const simRoute = await calculateSimulatorRouteDelay({
          origin_lat: caserne.latitude,
          origin_lng: caserne.longitude,
          destination_lat: selectedAlerte.latitude,
          destination_lng: selectedAlerte.longitude,
          emergency_mode: true,
        });

        if (simRoute && !isCancelled) {
          rawDuration = Math.round(simRoute.free_flow_duration_min);
          durationWithTraffic = Math.round(simRoute.traffic_duration_min);
          trafficDelay = Math.round(simRoute.delay_minutes);
          warningMsg = simRoute.warning || undefined;
        }
      }

      if (!isCancelled) {
        onRouteCalculated({
          caserne,
          alerte: selectedAlerte,
          distanceKm: dis,
          durationMinutes: rawDuration,
          durationWithTrafficMinutes: durationWithTraffic,
          trafficDelayMinutes: trafficDelay,
          warning: warningMsg,
          steps: [
            `Départ de la ${caserne.nom} (${caserne.adresse})`,
            'Engagement sur artère prioritaire (gyrophares et avertisseur deux-tons 198)',
            'Traversée rapide du corridor urbain sécurisé',
            `Arrivée sur le lieu de l'accident : ${selectedAlerte.adresse}`,
          ],
          polylineCoordinates: polyCoordinates,
        });
      }
    };

    computeAndNotifyRoute();

    return () => {
      isCancelled = true;
    };
  }, [selectedAlerte, selectedCaserne, trafficLayerActive, getNearestCaserne, onRouteCalculated]);

  // Bouton de recentrage rapide sur la zone Kélibia / Nord-Est Cap Bon
  const handleRecenter = () => {
    if (leafletMapRef.current) {
      const geoCfg = getGeoConfig();
      leafletMapRef.current.invalidateSize();
      leafletMapRef.current.fitBounds(getRegionLeafletBounds(geoCfg), { padding: [20, 20] });
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      {/* Conteneur principal de la carte */}
      <div
        ref={mapContainerRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          backgroundColor: '#0b111e',
        }}
      />

      {/* Boutons de contrôle tactique flottants */}
      <div
        style={{
          position: 'absolute',
          top: '80px',
          left: '12px',
          zIndex: 30,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        {/* Recentrage sur le Cap Bon */}
        <button
          onClick={handleRecenter}
          title="Recentrer la carte sur le Cap Bon (Gouvernorat de Nabeul)"
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '6px',
            width: '34px',
            height: '34px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#f8fafc',
            cursor: 'pointer',
            boxShadow: '0 4px 10px rgba(0, 0, 0, 0.4)',
            fontSize: '15px',
          }}
        >
          🎯
        </button>

        {/* Toggle Couche Risk Map */}
        <button
          onClick={() => setRiskMapLayerActive(!riskMapLayerActive)}
          title={riskMapLayerActive ? 'Masquer la couche Risk Map' : 'Afficher la couche Risk Map'}
          style={{
            backgroundColor: riskMapLayerActive ? 'rgba(239, 68, 68, 0.25)' : '#0f172a',
            border: riskMapLayerActive ? '1px solid #ef4444' : '1px solid #334155',
            borderRadius: '6px',
            width: '34px',
            height: '34px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: riskMapLayerActive ? '#fca5a5' : '#94a3b8',
            cursor: 'pointer',
            boxShadow: '0 4px 10px rgba(0, 0, 0, 0.4)',
            fontSize: '15px',
          }}
        >
          🛡️
        </button>
      </div>

    </div>
  );
};
