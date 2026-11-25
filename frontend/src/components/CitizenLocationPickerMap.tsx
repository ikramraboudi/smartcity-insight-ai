import React, { useEffect, useRef } from 'react';
import L from 'leaflet';

interface CitizenLocationPickerMapProps {
  latitude: number;
  longitude: number;
  onLocationChange: (lat: number, lng: number) => void;
}

export const CitizenLocationPickerMap: React.FC<CitizenLocationPickerMapProps> = ({
  latitude,
  longitude,
  onLocationChange,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onLocationChangeRef = useRef(onLocationChange);
  const initialCoordsRef = useRef({ latitude, longitude });

  useEffect(() => {
    onLocationChangeRef.current = onLocationChange;
  }, [onLocationChange]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const { latitude: initLat, longitude: initLng } = initialCoordsRef.current;

    const tunisBounds = L.latLngBounds(
      L.latLng(36.4, 9.8),
      L.latLng(37.2, 10.6)
    );

    const map = L.map(containerRef.current, {
      center: [initLat, initLng],
      zoom: 14,
      minZoom: 11,
      maxZoom: 18,
      maxBounds: tunisBounds,
      maxBoundsViscosity: 0.8,
    });

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);

    const pinIcon = L.divIcon({
      className: 'citizen-picker-pin',
      html: `<div style="
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: linear-gradient(135deg, #2563eb, #06b6d4);
        border: 3px solid #fff;
        box-shadow: 0 0 14px rgba(56, 189, 248, 0.85);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
      ">📍</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });

    const marker = L.marker([initLat, initLng], {
      icon: pinIcon,
      draggable: true,
    }).addTo(map);

    marker.on('dragend', () => {
      const pos = marker.getLatLng();
      onLocationChangeRef.current(
        Number(pos.lat.toFixed(6)),
        Number(pos.lng.toFixed(6))
      );
    });

    map.on('click', (e: L.LeafletMouseEvent) => {
      const newLat = Number(e.latlng.lat.toFixed(6));
      const newLng = Number(e.latlng.lng.toFixed(6));
      marker.setLatLng([newLat, newLng]);
      onLocationChangeRef.current(newLat, newLng);
    });

    mapRef.current = map;
    markerRef.current = marker;

    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });
    resizeObserver.observe(containerRef.current);

    const timer = setTimeout(() => map.invalidateSize(), 150);

    return () => {
      clearTimeout(timer);
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    const currentPos = markerRef.current.getLatLng();
    if (
      Math.abs(currentPos.lat - latitude) > 1e-6 ||
      Math.abs(currentPos.lng - longitude) > 1e-6
    ) {
      markerRef.current.setLatLng([latitude, longitude]);
      mapRef.current.panTo([latitude, longitude], { animate: true });
    }
  }, [latitude, longitude]);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: 220,
        borderRadius: 10,
        overflow: 'hidden',
        border: '1px solid var(--border-color)',
        backgroundColor: '#0b111e',
      }}
    >
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          left: 8,
          zIndex: 400,
          background: 'rgba(11, 17, 30, 0.88)',
          backdropFilter: 'blur(6px)',
          border: '1px solid var(--border-light)',
          borderRadius: 6,
          padding: '4px 10px',
          fontSize: 11,
          color: '#cbd5e1',
          pointerEvents: 'none',
        }}
      >
        Cliquez sur la carte ou glissez le repère pour ajuster la position exacte
      </div>
    </div>
  );
};
