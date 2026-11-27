import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { Construction, MapPin, Plus, Trash2 } from 'lucide-react';
import { addStandardBasemapLayer, getGeoConfig, getRegionLeafletBounds } from '../config/geoConfig';
import {
  createChantier,
  deleteChantier,
  fetchChantiers,
  updateChantierStatut,
} from '../services/api';
import type { Chantier, PrioriteChantier, StatutChantier } from '../types';

const CAP_BON_STREETS = [
  { id: 'seg_kelibia_centre', name: 'Avenue des Martyrs & Place du Marché (Kélibia)', lat: 36.8475, lng: 11.0939 },
  { id: 'seg_kelibia_port_mansourah', name: 'Route du Port & Corniche El Mansourah (Kélibia)', lat: 36.8408, lng: 11.1165 },
  { id: 'seg_hammam_ghezeze_c27', name: 'Route Côtière C27 — Kélibia / Hammam El Ghezaz', lat: 36.8906, lng: 11.1197 },
  { id: 'seg_dar_allouche_c27', name: 'C27 Nord — Hammam El Ghezaz / Dar Allouche', lat: 36.9350, lng: 11.1050 },
  { id: 'seg_kerkouane_littoral', name: 'Route Littorale — Dar Allouche / Kerkouane', lat: 36.9467, lng: 11.0989 },
  { id: 'seg_el_haouaria_centre', name: "Route d'El Haouaria (C27 / Route des Grottes)", lat: 37.0500, lng: 11.0144 },
  { id: 'seg_azmour_carrefour', name: 'Liaison Ouest — Kélibia / Azmour (Route de Takelsa)', lat: 36.8260, lng: 11.0180 },
  { id: 'seg_menzel_horr_mc27', name: 'Corridor MC27 — Kélibia / Menzel Horr', lat: 36.7361, lng: 10.9558 },
];

export const ChantiersPanel: React.FC = () => {
  const [chantiers, setChantiers] = useState<Chantier[]>([]);
  const [titre, setTitre] = useState('');
  const [streetId, setStreetId] = useState(CAP_BON_STREETS[0].id);
  const [rueNom, setRueNom] = useState(CAP_BON_STREETS[0].name);
  const [latitude, setLatitude] = useState(CAP_BON_STREETS[0].lat);
  const [longitude, setLongitude] = useState(CAP_BON_STREETS[0].lng);
  const [priorite, setPriorite] = useState<PrioriteChantier>('ELEVEE');
  const [voiesBloquees, setVoiesBloquees] = useState(1);
  const [statut, setStatut] = useState<StatutChantier>('EN_COURS');
  const [dateDebut, setDateDebut] = useState('');
  const [dateFin, setDateFin] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const mapRef = useRef<HTMLDivElement | null>(null);
  const leafletMapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  const loadChantiers = async () => {
    const data = await fetchChantiers();
    setChantiers(data);
  };

  useEffect(() => {
    loadChantiers();
  }, []);

  useEffect(() => {
    if (!mapRef.current || leafletMapRef.current) return;
    const cfg = getGeoConfig();
    const map = L.map(mapRef.current, {
      center: [latitude, longitude],
      zoom: 13,
      minZoom: cfg.map.min_zoom,
      maxZoom: cfg.map.max_zoom,
      maxBounds: getRegionLeafletBounds(cfg),
      maxBoundsViscosity: 0.75,
    });
    addStandardBasemapLayer(map);

    const icon = L.divIcon({
      className: 'custom-chantier-picker',
      html: '<div style="font-size:24px;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.6))">🚧</div>',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const marker = L.marker([latitude, longitude], { icon, draggable: true }).addTo(map);
    marker.on('dragend', () => {
      const pos = marker.getLatLng();
      setLatitude(Number(pos.lat.toFixed(5)));
      setLongitude(Number(pos.lng.toFixed(5)));
    });

    map.on('click', (e: L.LeafletMouseEvent) => {
      const lat = Number(e.latlng.lat.toFixed(5));
      const lng = Number(e.latlng.lng.toFixed(5));
      setLatitude(lat);
      setLongitude(lng);
      marker.setLatLng([lat, lng]);
    });

    leafletMapRef.current = map;
    markerRef.current = marker;

    return () => {
      map.remove();
      leafletMapRef.current = null;
      markerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (markerRef.current && leafletMapRef.current) {
      markerRef.current.setLatLng([latitude, longitude]);
      leafletMapRef.current.panTo([latitude, longitude]);
    }
  }, [latitude, longitude]);

  const handleStreetChange = (selectedId: string) => {
    setStreetId(selectedId);
    const found = CAP_BON_STREETS.find((s) => s.id === selectedId);
    if (found) {
      setRueNom(found.name);
      setLatitude(found.lat);
      setLongitude(found.lng);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!titre.trim() || !rueNom.trim()) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      await createChantier({
        titre: titre.trim(),
        rue_nom: rueNom.trim(),
        street_id: streetId,
        description: description.trim(),
        latitude,
        longitude,
        priorite,
        voies_bloquees: voiesBloquees,
        statut,
        date_debut: dateDebut || undefined,
        date_fin: dateFin || undefined,
      });
      setTitre('');
      setDescription('');
      setFeedback('✅ Chantier déclaré et publié sur la carte Protection Civile.');
      await loadChantiers();
    } catch (err: any) {
      setFeedback(`❌ ${err?.response?.data?.detail || 'Erreur lors de la déclaration du chantier.'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatutChange = async (id: number, newStatut: StatutChantier) => {
    await updateChantierStatut(id, newStatut);
    await loadChantiers();
  };

  const handleDelete = async (id: number) => {
    await deleteChantier(id);
    await loadChantiers();
  };

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: 14,
        padding: 20,
        marginBottom: 24,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Construction size={20} color="#f59e0b" />
          <div>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: 'var(--text-main)' }}>
              Déclaration & Suivi des Chantiers de Voirie
            </h2>
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-muted)' }}>
              Les chantiers actifs (🚧) apparaissent automatiquement sur la carte de la Protection Civile.
            </p>
          </div>
        </div>
        <span
          style={{
            padding: '4px 10px',
            borderRadius: 20,
            fontSize: 12,
            fontWeight: 700,
            background: 'rgba(245, 158, 11, 0.15)',
            color: '#fbbf24',
          }}
        >
          {chantiers.filter((c) => c.statut !== 'TERMINE').length} actif(s) sur carte
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
        {/* Formulaire de déclaration */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input
            type="text"
            placeholder="Titre du chantier (ex: Réfection chaussée)"
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
            required
            style={{
              padding: '9px 12px',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-dark)',
              color: 'var(--text-main)',
              fontSize: 13,
            }}
          />

          <select
            value={streetId}
            onChange={(e) => handleStreetChange(e.target.value)}
            style={{
              padding: '9px 12px',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-dark)',
              color: 'var(--text-main)',
              fontSize: 13,
            }}
          >
            {CAP_BON_STREETS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Nom précis de la rue"
            value={rueNom}
            onChange={(e) => setRueNom(e.target.value)}
            required
            style={{
              padding: '9px 12px',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-dark)',
              color: 'var(--text-main)',
              fontSize: 13,
            }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <select
              value={priorite}
              onChange={(e) => setPriorite(e.target.value as PrioriteChantier)}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-dark)',
                color: 'var(--text-main)',
                fontSize: 12.5,
              }}
            >
              <option value="FAIBLE">Priorité Faible</option>
              <option value="MOYENNE">Priorité Moyenne</option>
              <option value="ELEVEE">Priorité Élevée</option>
              <option value="CRITIQUE">Priorité Critique</option>
            </select>

            <input
              type="number"
              min={1}
              max={6}
              value={voiesBloquees}
              onChange={(e) => setVoiesBloquees(Math.max(1, Number(e.target.value)))}
              title="Voies bloquées"
              placeholder="Voies"
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-dark)',
                color: 'var(--text-main)',
                fontSize: 12.5,
              }}
            />

            <select
              value={statut}
              onChange={(e) => setStatut(e.target.value as StatutChantier)}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-dark)',
                color: 'var(--text-main)',
                fontSize: 12.5,
              }}
            >
              <option value="EN_COURS">En cours</option>
              <option value="PLANIFIE">Planifié</option>
              <option value="TERMINE">Terminé</option>
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <input
              type="date"
              value={dateDebut}
              onChange={(e) => setDateDebut(e.target.value)}
              title="Date début"
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-dark)',
                color: 'var(--text-main)',
                fontSize: 12.5,
              }}
            />
            <input
              type="date"
              value={dateFin}
              onChange={(e) => setDateFin(e.target.value)}
              title="Date fin"
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-dark)',
                color: 'var(--text-main)',
                fontSize: 12.5,
              }}
            />
          </div>

          <textarea
            rows={2}
            placeholder="Détails / déviation conseillée (optionnel)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-dark)',
              color: 'var(--text-main)',
              fontSize: 12.5,
              resize: 'vertical',
            }}
          />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <MapPin size={13} color="#f59e0b" /> {latitude}, {longitude} (cliquez sur la carte pour ajuster)
            </span>
          </div>

          <button
            type="submit"
            disabled={submitting}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '10px 14px',
              borderRadius: 8,
              border: 'none',
              background: '#f59e0b',
              color: '#0f172a',
              fontWeight: 700,
              fontSize: 13.5,
              cursor: 'pointer',
            }}
          >
            <Plus size={16} /> {submitting ? 'Publication...' : 'Déclarer le chantier'}
          </button>

          {feedback && (
            <div style={{ fontSize: 12.5, color: feedback.startsWith('✅') ? '#34d399' : '#f87171' }}>
              {feedback}
            </div>
          )}
        </form>

        {/* Carte de sélection + Liste */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div
            ref={mapRef}
            style={{
              height: 210,
              borderRadius: 10,
              overflow: 'hidden',
              border: '1px solid var(--border-color)',
            }}
          />

          <div style={{ maxHeight: 190, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {chantiers.length === 0 ? (
              <div style={{ fontSize: 12.5, color: 'var(--text-dim)', padding: 10, textAlign: 'center' }}>
                Aucun chantier déclaré pour le moment.
              </div>
            ) : (
              chantiers.map((c) => (
                <div
                  key={c.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: '8px 10px',
                    borderRadius: 8,
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      🚧 {c.titre}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                      {c.rue_nom} • {c.voies_bloquees} voie(s) • {c.priorite}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <select
                      value={c.statut}
                      onChange={(e) => handleStatutChange(c.id, e.target.value as StatutChantier)}
                      style={{
                        padding: '4px 6px',
                        borderRadius: 6,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-card)',
                        color: 'var(--text-main)',
                        fontSize: 11.5,
                      }}
                    >
                      <option value="PLANIFIE">Planifié</option>
                      <option value="EN_COURS">En cours</option>
                      <option value="TERMINE">Terminé</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => handleDelete(c.id)}
                      title="Supprimer"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#ef4444',
                        cursor: 'pointer',
                        padding: 4,
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
