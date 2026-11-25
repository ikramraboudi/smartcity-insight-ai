import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock,
  FileText,
  Flame,
  Loader2,
  Map as MapIcon,
  MapPin,
  Send,
  Shield,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import { getGeoConfig } from '../config/geoConfig';
import { createSignalement, saveCitizenReportId } from '../services/api';
import {
  CategorieSignalement,
  GraviteSignalement,
  Signalement,
} from '../types';
import { CitizenLocationPickerMap } from './CitizenLocationPickerMap';
import { CitizenTrackingView } from './CitizenTrackingView';

const CATEGORIES: {
  value: CategorieSignalement;
  label: string;
  icon: string;
  desc: string;
}[] = [
  {
    value: 'NID_DE_POULE',
    label: 'Nid-de-poule',
    icon: '🕳️',
    desc: 'Chaussée dégradée, trou sur la route',
  },
  {
    value: 'DECHETS',
    label: 'Déchets / Voirie',
    icon: '🗑️',
    desc: 'Dépôt sauvage, poubelle débordante',
  },
  {
    value: 'ACCIDENT',
    label: 'Accident',
    icon: '💥',
    desc: 'Collision, obstacle routier urgent',
  },
  {
    value: 'ECLAIRAGE',
    label: 'Éclairage public',
    icon: '💡',
    desc: 'Lampadaire éteint ou clignotant',
  },
  {
    value: 'SIGNALISATION',
    label: 'Signalisation',
    icon: '🛑',
    desc: 'Panneau abîmé, feu tricolore en panne',
  },
  {
    value: 'AUTRE',
    label: 'Autre incident',
    icon: '⚠️',
    desc: 'Tout autre problème sur la voie publique',
  },
];

const GRAVITES: {
  value: GraviteSignalement;
  label: string;
  color: string;
  bg: string;
}[] = [
  {
    value: 'FAIBLE',
    label: 'Faible',
    color: '#10b981',
    bg: 'rgba(16, 185, 129, 0.15)',
  },
  {
    value: 'MOYENNE',
    label: 'Moyenne',
    color: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.15)',
  },
  {
    value: 'ELEVEE',
    label: 'Élevée',
    color: '#f97316',
    bg: 'rgba(249, 115, 22, 0.15)',
  },
  {
    value: 'CRITIQUE',
    label: 'Critique',
    color: '#ef4444',
    bg: 'rgba(239, 68, 68, 0.2)',
  },
];

export const CitizenReportForm: React.FC = () => {
  const geoCfg = getGeoConfig();
  const [activeTab, setActiveTab] = useState<'report' | 'tracking'>('report');
  const [highlightReportId, setHighlightReportId] = useState<string | null>(null);

  const [categorie, setCategorie] = useState<CategorieSignalement>('NID_DE_POULE');
  const [gravite, setGravite] = useState<GraviteSignalement>('MOYENNE');
  const [description, setDescription] = useState('');
  const [adresseTexte, setAdresseTexte] = useState('');
  const [quartier, setQuartier] = useState(geoCfg.default_city);
  const [latitude, setLatitude] = useState<number>(geoCfg.default_coords.latitude);
  const [longitude, setLongitude] = useState<number>(geoCfg.default_coords.longitude);
  const [isGeolocating, setIsGeolocating] = useState(false);
  const [gpsStatusText, setGpsStatusText] = useState<string>('Détection GPS...');

  // Gestion de la photo
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  // États du formulaire
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successResult, setSuccessResult] = useState<Signalement | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [duplicateReportId, setDuplicateReportId] = useState<string | null>(null);

  // Géolocalisation via l'API navigateur
  const handleGeolocate = useCallback((silentFallback = false) => {
    const fallbackCfg = getGeoConfig();
    if (!navigator.geolocation) {
      if (!silentFallback) {
        alert("La géolocalisation n'est pas supportée par votre navigateur.");
      }
      setGpsStatusText(`Position par défaut (${fallbackCfg.default_city}) — ajustez sur la carte`);
      return;
    }
    setIsGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLatitude(Number(pos.coords.latitude.toFixed(6)));
        setLongitude(Number(pos.coords.longitude.toFixed(6)));
        setGpsStatusText('Position GPS détectée automatiquement');
        setIsGeolocating(false);
      },
      (err) => {
        console.warn('Erreur géolocalisation:', err);
        setLatitude(fallbackCfg.default_coords.latitude);
        setLongitude(fallbackCfg.default_coords.longitude);
        setGpsStatusText(`Position par défaut (${fallbackCfg.default_city}) — cliquez sur la carte pour préciser`);
        setIsGeolocating(false);
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  }, []);

  // Géolocalisation GPS automatique au chargement
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) {
        handleGeolocate(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [handleGeolocate]);

  const handleMapLocationChange = useCallback((lat: number, lng: number) => {
    setLatitude(lat);
    setLongitude(lng);
    setGpsStatusText('Position ajustée manuellement sur la carte');
  }, []);

  // Sélection et preview de la photo
  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhotoFile(file);
      const previewUrl = URL.createObjectURL(file);
      setPhotoPreview(previewUrl);
    }
  };

  const handleRemovePhoto = () => {
    setPhotoFile(null);
    if (photoPreview) {
      URL.revokeObjectURL(photoPreview);
    }
    setPhotoPreview(null);
  };

  // Soumission du signalement
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setIsRateLimited(false);
    setDuplicateReportId(null);

    try {
      const formData = new FormData();
      formData.append('categorie', categorie);
      formData.append('gravite', gravite);
      formData.append('description', description);
      formData.append('latitude', latitude.toString());
      formData.append('longitude', longitude.toString());
      formData.append('adresse_texte', adresseTexte || quartier);
      formData.append('quartier', quartier);

      if (photoFile) {
        formData.append('photo_floutee', photoFile);
      }

      const result = await createSignalement(formData);
      saveCitizenReportId(result.id);
      setHighlightReportId(result.id);
      setSuccessResult(result);
      // Réinitialisation du formulaire
      setDescription('');
      setAdresseTexte('');
      handleRemovePhoto();
    } catch (err: any) {
      console.error('Erreur soumission signalement:', err);
      if (err.response?.status === 429) {
        setIsRateLimited(true);
        setErrorMessage(
          '⚠️ Limite anti-spam atteinte : quota horaire dépassé pour protéger la plateforme contre les faux signalements.'
        );
      } else if (err.response?.status === 409) {
        setIsRateLimited(true);
        const dupId = err.response?.data?.doublon_id || null;
        setDuplicateReportId(dupId);
        setErrorMessage(
          `ℹ️ ${err.response?.data?.detail || 'Un signalement similaire a déjà été enregistré à proximité.'}`
        );
      } else {
        const detail =
          err.response?.data?.detail ||
          err.response?.data?.error ||
          err.message ||
          'Une erreur est survenue lors de la transmission du signalement.';
        setErrorMessage(`❌ Échec de la transmission : ${detail}`);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '24px 16px' }}>
      {/* En-tête */}
      <div style={{ marginBottom: 20, textAlign: 'center' }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 14px',
            borderRadius: 20,
            background: 'rgba(59, 130, 246, 0.12)',
            color: '#60a5fa',
            fontSize: 13,
            fontWeight: 600,
            marginBottom: 10,
          }}
        >
          <Zap size={15} /> Portail Citoyen SmartCity {geoCfg.region_short_name}
        </div>
        <h1 style={{ fontSize: 'clamp(22px, 4vw, 28px)', fontWeight: 700, color: 'var(--text-main)', marginBottom: 8 }}>
          Espace Participatif Citoyen
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13.5, maxWidth: 640, margin: '0 auto 18px' }}>
          Signalez une anomalie urbaine avec anonymisation INPDP automatique, ou suivez en direct
          l'intervention des services municipaux sur la carte du {geoCfg.region_name}.
        </p>

        {/* Barre d'onglets harmonisée */}
        <div
          style={{
            display: 'inline-flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: 8,
            padding: 6,
            borderRadius: 12,
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('report')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '9px 18px',
              borderRadius: 8,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13.5,
              fontWeight: 600,
              background: activeTab === 'report' ? 'linear-gradient(135deg, #2563eb, #0284c7)' : 'transparent',
              color: activeTab === 'report' ? '#fff' : 'var(--text-muted)',
              boxShadow: activeTab === 'report' ? '0 2px 10px rgba(37, 99, 235, 0.35)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <FileText size={15} />
            <span>Signaler un incident</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('tracking')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '9px 18px',
              borderRadius: 8,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13.5,
              fontWeight: 600,
              background: activeTab === 'tracking' ? 'linear-gradient(135deg, #059669, #0d9488)' : 'transparent',
              color: activeTab === 'tracking' ? '#fff' : 'var(--text-muted)',
              boxShadow: activeTab === 'tracking' ? '0 2px 10px rgba(16, 185, 129, 0.35)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <MapIcon size={15} />
            <span>Carte & Suivi des signalements</span>
          </button>
        </div>
      </div>

      {activeTab === 'tracking' ? (
        <CitizenTrackingView highlightReportId={highlightReportId} />
      ) : (
        <div style={{ maxWidth: 860, margin: '0 auto' }}>
          {/* Message de confirmation de succès */}
          {successResult && (
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: 12,
                padding: 20,
                marginBottom: 24,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <CheckCircle2 size={24} color="#10b981" />
                <div>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: '#10b981' }}>
                    Signalement enregistré avec succès !
                  </h3>
                  <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    Identifiant : <code style={{ color: '#38bdf8' }}>{successResult.id}</code>
                  </p>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 16,
                  background: 'rgba(0, 0, 0, 0.25)',
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 13,
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Catégorie : </span>
                  <strong>{successResult.categorie}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Quartier : </span>
                  <strong>{successResult.quartier}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Statut : </span>
                  <span
                    style={{
                      background: 'rgba(59, 130, 246, 0.2)',
                      color: '#60a5fa',
                      padding: '2px 8px',
                      borderRadius: 10,
                      fontSize: 12,
                    }}
                  >
                    {successResult.statut}
                  </span>
                </div>
                {successResult.visages_plaques_floutes && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#10b981' }}>
                    <Shield size={14} />
                    <span>
                      Floutage IA INPDP appliqué ({successResult.nb_zones_floutees} zone(s) anonymisée(s))
                    </span>
                  </div>
                )}
                {successResult.alerte_liee && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#f87171' }}>
                    <Flame size={14} />
                    <span>
                      Alerte transmise en direct à la Protection Civile (Alerte #{successResult.alerte_liee})
                    </span>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
                <button
                  type="button"
                  onClick={() => {
                    setHighlightReportId(successResult.id);
                    setActiveTab('tracking');
                  }}
                  style={{
                    background: 'rgba(16, 185, 129, 0.2)',
                    border: '1px solid rgba(16, 185, 129, 0.45)',
                    color: '#34d399',
                    padding: '7px 14px',
                    borderRadius: 6,
                    fontSize: 13,
                    cursor: 'pointer',
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <MapIcon size={14} />
                  <span>Voir sur la carte & suivre l'avancement</span>
                </button>
                <button
                  type="button"
                  onClick={() => setSuccessResult(null)}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(148, 163, 184, 0.35)',
                    color: 'var(--text-muted)',
                    padding: '7px 14px',
                    borderRadius: 6,
                    fontSize: 13,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Fermer
                </button>
              </div>
            </div>
          )}

          {/* Message d'erreur / Rate Limiting / Doublon */}
          {errorMessage && (
            <div
              style={{
                background: isRateLimited ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                border: `1px solid ${isRateLimited ? 'rgba(245, 158, 11, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
                borderRadius: 12,
                padding: 16,
                marginBottom: 24,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
              }}
            >
              {isRateLimited ? (
                <Clock size={20} color="#f59e0b" style={{ flexShrink: 0, marginTop: 2 }} />
              ) : (
                <AlertTriangle size={20} color="#ef4444" style={{ flexShrink: 0, marginTop: 2 }} />
              )}
              <div style={{ flex: 1, fontSize: 13.5, lineHeight: 1.5, color: 'var(--text-main)' }}>
                <div>{errorMessage}</div>
                {duplicateReportId && (
                  <button
                    type="button"
                    onClick={() => {
                      setHighlightReportId(duplicateReportId);
                      setActiveTab('tracking');
                    }}
                    style={{
                      marginTop: 8,
                      background: 'rgba(56, 189, 248, 0.15)',
                      border: '1px solid rgba(56, 189, 248, 0.35)',
                      color: '#38bdf8',
                      borderRadius: 6,
                      padding: '5px 10px',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Consulter le signalement existant sur la carte →
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  setErrorMessage(null);
                  setDuplicateReportId(null);
                }}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={16} />
              </button>
            </div>
          )}

      {/* Formulaire principal */}
      <form
        onSubmit={handleSubmit}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 16,
          padding: 24,
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.3)',
        }}
      >
        {/* 1. Sélection de la catégorie */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--text-main)' }}>
            1. Type d'anomalie <span style={{ color: '#ef4444' }}>*</span>
          </label>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
              gap: 10,
            }}
          >
            {CATEGORIES.map((cat) => {
              const isSelected = categorie === cat.value;
              return (
                <button
                  key={cat.value}
                  type="button"
                  onClick={() => setCategorie(cat.value)}
                  style={{
                    background: isSelected ? 'rgba(59, 130, 246, 0.15)' : 'var(--bg-dark)',
                    border: `2px solid ${isSelected ? '#3b82f6' : 'var(--border-color)'}`,
                    borderRadius: 10,
                    padding: '12px 8px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span style={{ fontSize: 24 }}>{cat.icon}</span>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: isSelected ? '#60a5fa' : 'var(--text-main)',
                    }}
                  >
                    {cat.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 2. Sélection de la gravité */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 10, color: 'var(--text-main)' }}>
            2. Niveau de gravité estimé
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 10 }}>
            {GRAVITES.map((g) => {
              const isSelected = gravite === g.value;
              return (
                <button
                  key={g.value}
                  type="button"
                  onClick={() => setGravite(g.value)}
                  style={{
                    background: isSelected ? g.bg : 'var(--bg-dark)',
                    border: `1.5px solid ${isSelected ? g.color : 'var(--border-color)'}`,
                    color: isSelected ? g.color : 'var(--text-muted)',
                    borderRadius: 8,
                    padding: '10px 4px',
                    fontWeight: 600,
                    fontSize: 13,
                    cursor: 'pointer',
                    textAlign: 'center',
                  }}
                >
                  {g.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 3. Description textuelle */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <label style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-main)' }}>
              3. Description des faits <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              {description.length} / 1000
            </span>
          </div>
          <textarea
            required
            maxLength={1000}
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Décrivez précisément l'anomalie constatée (ex: gros trou sur la voie droite, déchets encombrants le trottoir...)"
            style={{
              width: '100%',
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: 12,
              color: 'var(--text-main)',
              fontSize: 14,
              resize: 'vertical',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
        </div>

        {/* 4. Localisation & Quartier */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 10, color: 'var(--text-main)' }}>
            4. Localisation (GPS automatique & carte interactive)
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 12 }}>
            <div>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                Délégation / Commune
              </span>
              <select
                value={quartier}
                onChange={(e) => setQuartier(e.target.value)}
                style={{
                  width: '100%',
                  background: 'var(--bg-dark)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  color: 'var(--text-main)',
                  fontSize: 13,
                  outline: 'none',
                }}
              >
                {geoCfg.delegation_names.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                Adresse approximative
              </span>
              <input
                type="text"
                value={adresseTexte}
                onChange={(e) => setAdresseTexte(e.target.value)}
                placeholder={`Ex: ${geoCfg.default_address}`}
                style={{
                  width: '100%',
                  background: 'var(--bg-dark)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  color: 'var(--text-main)',
                  fontSize: 13,
                  outline: 'none',
                }}
              />
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 13,
              marginBottom: 12,
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                <MapPin size={16} color="#38bdf8" />
                <span>
                  GPS :{' '}
                  <strong style={{ color: 'var(--text-main)' }}>
                    {latitude}, {longitude}
                  </strong>
                </span>
              </div>
              <span style={{ fontSize: 11.5, color: '#34d399', paddingLeft: 24 }}>{gpsStatusText}</span>
            </div>
            <button
              type="button"
              onClick={() => handleGeolocate(false)}
              disabled={isGeolocating}
              style={{
                background: 'rgba(56, 189, 248, 0.15)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                color: '#38bdf8',
                borderRadius: 6,
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {isGeolocating ? <Loader2 size={13} className="animate-spin" /> : <MapPin size={13} />}
              {isGeolocating ? 'Recherche...' : 'Me géolocaliser'}
            </button>
          </div>

          <CitizenLocationPickerMap
            latitude={latitude}
            longitude={longitude}
            onLocationChange={handleMapLocationChange}
          />
        </div>

        {/* 5. Téléversement de photo & Information INPDP */}
        <div style={{ marginBottom: 28 }}>
          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text-main)' }}>
            5. Photographie du problème (optionnel)
          </label>

          {/* Bandeau d'information Confidentialité INPDP */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 12.5,
              color: '#34d399',
              marginBottom: 12,
            }}
          >
            <Shield size={18} style={{ flexShrink: 0 }} />
            <span>
              <strong>Garantie INPDP :</strong> Les visages et plaques d'immatriculation seront
              automatiquement floutés par IA, et les données personnelles EXIF/GPS de votre appareil
              seront purgées avant enregistrement.
            </span>
          </div>

          {!photoPreview ? (
            <label
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                background: 'var(--bg-dark)',
                border: '2px dashed var(--border-color)',
                borderRadius: 12,
                padding: '24px 16px',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                transition: 'border-color 0.2s',
              }}
            >
              <Camera size={28} color="#60a5fa" />
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-main)' }}>
                Cliquez pour ajouter une photo ou glissez-déposez ici
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                Formats acceptés : JPG, JPEG, PNG (max 10 Mo)
              </span>
              <input
                type="file"
                accept="image/*"
                onChange={handlePhotoChange}
                style={{ display: 'none' }}
              />
            </label>
          ) : (
            <div
              style={{
                position: 'relative',
                background: 'var(--bg-dark)',
                border: '1px solid var(--border-color)',
                borderRadius: 12,
                padding: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 16,
              }}
            >
              <img
                src={photoPreview}
                alt="Aperçu avant floutage"
                style={{
                  width: 90,
                  height: 90,
                  objectFit: 'cover',
                  borderRadius: 8,
                  border: '1px solid var(--border-color)',
                }}
              />
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-main)', marginBottom: 4 }}>
                  {photoFile?.name}
                </p>
                <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {photoFile ? (photoFile.size / 1024 / 1024).toFixed(2) : 0} Mo • Prêt pour floutage IA
                </p>
              </div>
              <button
                type="button"
                onClick={handleRemovePhoto}
                style={{
                  background: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#ef4444',
                  borderRadius: 6,
                  padding: 8,
                  cursor: 'pointer',
                }}
                title="Supprimer la photo"
              >
                <Trash2 size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Bouton de soumission */}
        <button
          type="submit"
          disabled={isSubmitting}
          style={{
            width: '100%',
            background: isSubmitting ? 'var(--border-color)' : 'linear-gradient(135deg, #2563eb, #1d4ed8)',
            border: 'none',
            borderRadius: 10,
            padding: '14px 20px',
            color: '#fff',
            fontSize: 15,
            fontWeight: 700,
            cursor: isSubmitting ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            boxShadow: '0 4px 15px rgba(37, 99, 235, 0.35)',
            transition: 'opacity 0.2s',
          }}
        >
          {isSubmitting ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>Anonymisation IA & Transmission...</span>
            </>
          ) : (
            <>
              <Send size={18} />
              <span>Envoyer le signalement</span>
            </>
          )}
        </button>
      </form>
        </div>
      )}
    </div>
  );
};
