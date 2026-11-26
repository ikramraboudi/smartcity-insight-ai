import L from 'leaflet';
import type { Caserne } from '../types';

export interface GeoBoundsConfig {
  south_west: [number, number];
  north_east: [number, number];
}

export interface GeoMapConfig {
  center: [number, number];
  default_point: [number, number];
  zoom: number;
  picker_zoom: number;
  min_zoom: number;
  max_zoom: number;
  bounds: GeoBoundsConfig;
}

export interface GeoLocality {
  id: string;
  nom: string;
  code_postal: string;
  lat: number;
  lng: number;
}

export interface GeoConfig {
  region_id: string;
  region_name: string;
  region_short_name: string;
  default_city: string;
  default_address: string;
  default_coords: {
    latitude: number;
    longitude: number;
  };
  map: GeoMapConfig;
  delegations: GeoLocality[];
  delegation_names: string[];
  circonscriptions: string[];
}

export const MAP_CENTER: [number, number] = [36.935, 11.055];
export const MAP_ZOOM = 12;
export const MAP_MIN_ZOOM = 11;
export const MAP_BOUNDS: [[number, number], [number, number]] = [
  [36.80, 10.94],
  [37.09, 11.15],
];

export const STANDARD_BASEMAP_URL =
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

export function addStandardBasemapLayer(map: L.Map): void {
  L.tileLayer(STANDARD_BASEMAP_URL, {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map);
}

export const LOCALITES_CAP_BON_NE: GeoLocality[] = [
  { id: 'kelibia', nom: 'Kélibia', code_postal: '8090', lat: 36.8475, lng: 11.0939 },
  { id: 'hammam_ghezeze', nom: 'Hammam El Ghezaz', code_postal: '8025', lat: 36.8906, lng: 11.1197 },
  { id: 'el_haouaria', nom: 'El Haouaria', code_postal: '8045', lat: 37.0500, lng: 11.0144 },
  { id: 'dar_allouche', nom: 'Dar Allouche', code_postal: '8055', lat: 36.9350, lng: 11.1050 },
  { id: 'kerkouane', nom: 'Kerkouane', code_postal: '8045', lat: 36.9467, lng: 11.0989 },
  { id: 'azmour', nom: 'Azmour', code_postal: '8035', lat: 36.8260, lng: 11.0180 },
  { id: 'menzel_horr', nom: 'Menzel Horr', code_postal: '8015', lat: 36.7361, lng: 10.9558 },
];

/**
 * Configuration géographique centralisée par défaut :
 * Nord-Est du Cap Bon (Kélibia, Hammam El Ghezaz, El Haouaria, Dar Allouche, Kerkouane, Azmour, Menzel Horr).
 * Hydratée dynamiquement via GET /api/urgences/geo-config/.
 */
export const DEFAULT_GEO_CONFIG: GeoConfig = {
  region_id: 'cap_bon_ne',
  region_name: 'Nord-Est Cap Bon (Kélibia • Hammam El Ghezaz • El Haouaria)',
  region_short_name: 'Kélibia / Cap Bon NE',
  default_city: 'Kélibia',
  default_address: 'Avenue des Martyrs, Kélibia',
  default_coords: {
    latitude: 36.8475,
    longitude: 11.0939,
  },
  map: {
    center: MAP_CENTER,
    default_point: [36.8475, 11.0939],
    zoom: MAP_ZOOM,
    picker_zoom: 13,
    min_zoom: MAP_MIN_ZOOM,
    max_zoom: 18,
    bounds: {
      south_west: MAP_BOUNDS[0],
      north_east: MAP_BOUNDS[1],
    },
  },
  delegations: LOCALITES_CAP_BON_NE,
  delegation_names: LOCALITES_CAP_BON_NE.map((d) => d.nom),
  circonscriptions: LOCALITES_CAP_BON_NE.map(
    (d) => `Commune ${d.nom} (${d.code_postal})`
  ),
};

export const FALLBACK_CASERNES_CAP_BON: Caserne[] = [
  {
    id: 'caserne-kelibia',
    nom: 'Protection Civile Kélibia',
    adresse: "Avenue des Martyrs / Avenue de l'Environnement, 8090 Kélibia",
    latitude: 36.8475,
    longitude: 11.0939,
    telephone: '198 / 72 296 366',
    ambulances_disponibles: 3,
    camions_disponibles: 2,
    statut: 'OPERATIONNELLE',
  },
  {
    id: 'caserne-el-haouaria',
    nom: 'Protection civile El Haouaria',
    adresse: 'Croisement des routes MC 26 et MC 27, 8045 El Haouaria',
    latitude: 37.05,
    longitude: 11.0144,
    telephone: '198 / 72 269 575',
    ambulances_disponibles: 2,
    camions_disponibles: 2,
    statut: 'OPERATIONNELLE',
  },
];

let activeGeoConfig: GeoConfig = DEFAULT_GEO_CONFIG;

export function getGeoConfig(): GeoConfig {
  return activeGeoConfig;
}

export function setGeoConfig(next: Partial<GeoConfig>): GeoConfig {
  activeGeoConfig = {
    ...activeGeoConfig,
    ...next,
    default_coords: next.default_coords ?? activeGeoConfig.default_coords,
    map: next.map ?? activeGeoConfig.map,
    delegations: next.delegations ?? activeGeoConfig.delegations,
  };
  return activeGeoConfig;
}

export function getRegionLeafletBounds(cfg: GeoConfig = activeGeoConfig): L.LatLngBounds {
  return L.latLngBounds(
    L.latLng(cfg.map.bounds.south_west[0], cfg.map.bounds.south_west[1]),
    L.latLng(cfg.map.bounds.north_east[0], cfg.map.bounds.north_east[1])
  );
}

/**
 * Ajoute des badges permanents lisibles pour chaque localité de la zone.
 */
export function renderLocalityLabelsLayer(
  layer: L.LayerGroup,
  localities: GeoLocality[] = activeGeoConfig.delegations
): void {
  layer.clearLayers();
  const placementById: Record<string, { direction: L.Direction; offset: [number, number] }> = {
    dar_allouche: { direction: 'left', offset: [-8, 2] },
    kerkouane: { direction: 'right', offset: [8, -4] },
  };
  localities.forEach((loc) => {
    const placement = placementById[loc.id] ?? { direction: 'top' as L.Direction, offset: [0, -8] as [number, number] };
    const anchor = L.circleMarker([loc.lat, loc.lng], {
      radius: 2.5,
      color: '#38bdf8',
      weight: 1,
      fillColor: '#f8fafc',
      fillOpacity: 0.9,
      interactive: false,
    });
    anchor.bindTooltip(loc.nom, {
      permanent: true,
      direction: placement.direction,
      offset: placement.offset,
      className: 'capbon-locality-label',
    });
    anchor.addTo(layer);
  });
}
