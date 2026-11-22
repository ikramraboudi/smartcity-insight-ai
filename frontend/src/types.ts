export type StatutAlerte =
  | 'A_CONFIRMER'
  | 'CONFIRME'
  | 'PRISE_EN_CHARGE'
  | 'EN_INTERVENTION'
  | 'CLOTURE';

export type GraviteAlerte = 'FAIBLE' | 'MOYENNE' | 'GRAVE';

export interface Alerte {
  id: number;
  statut: StatutAlerte;
  gravite: GraviteAlerte;
  adresse: string;
  latitude: number;
  longitude: number;
  nb_signalements: number;
  date_creation?: string;
  date_confirmation?: string | null;
  date_prise_en_charge?: string | null;
  date_en_intervention?: string | null;
  date_cloture?: string | null;
}

export interface Caserne {
  id: string;
  nom: string;
  adresse: string;
  latitude: number;
  longitude: number;
  telephone: string;
  ambulances_disponibles: number;
  camions_disponibles: number;
  statut: string;
}

export interface RouteInfo {
  caserne: Caserne;
  alerte: Alerte;
  distanceKm: number;
  durationMinutes: number;
  durationWithTrafficMinutes?: number;
  trafficDelayMinutes?: number;
  warning?: string;
  steps: string[];
  polylineCoordinates?: [number, number][];
}

export interface RiskMapResult {
  score_risque_pourcentage: number;
  niveau_risk_map: string;
  facteurs_explicatifs: string[];
}

// =============================================================================
// Module Signalements Citoyens & Dashboard Municipal (Étudiant 2)
// =============================================================================

export type CategorieSignalement =
  | 'ACCIDENT'
  | 'NID_DE_POULE'
  | 'ECLAIRAGE'
  | 'DECHETS'
  | 'SIGNALISATION'
  | 'AUTRE';

export type GraviteSignalement = 'FAIBLE' | 'MOYENNE' | 'ELEVEE' | 'CRITIQUE';

export type StatutSignalement =
  | 'EN_ATTENTE'
  | 'CONFIRME'
  | 'EN_COURS'
  | 'RESOLU'
  | 'REJETE_SPAM';

export interface Signalement {
  id: string;
  categorie: CategorieSignalement;
  gravite: GraviteSignalement;
  description: string;
  latitude: number;
  longitude: number;
  adresse_texte: string;
  quartier: string;
  photo_floutee?: string | null;
  visages_plaques_floutes: boolean;
  nb_zones_floutees: number;
  statut: StatutSignalement;
  alerte_liee?: number | null;
  ip_emetteur?: string | null;
  date_creation: string;
  date_mise_a_jour?: string;
}

export interface CreateSignalementPayload {
  categorie: CategorieSignalement;
  gravite: GraviteSignalement;
  description: string;
  latitude: number;
  longitude: number;
  adresse_texte?: string;
  quartier?: string;
  photo?: File | null;
}

export type UserRole = 'CITOYEN' | 'RESPONSABLE_MUNICIPAL';

export type PlatformRole = 'RESPONSABLE_MUNICIPAL' | 'CITOYEN' | 'PROTECTION_CIVILE';

export type AuthMode = 'LOGIN' | 'REGISTER';

export interface UserSession {
  id?: number | string;
  username: string;
  email: string;
  role: PlatformRole;
  est_responsable_municipal?: boolean;
  code_arrondissement?: string;
  telephone_cin?: string;
  matricule_agent?: string;
  token?: string;
}

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  est_responsable_municipal: boolean;
}

export interface LoginResponse {
  access: string;
  token_type: 'Bearer';
  user: AuthUser;
}

export interface SignalementStatistiques {
  total_signalements: number;
  par_statut: Record<string, number>;
  par_categorie: Record<string, number>;
  par_gravite: Record<string, number>;
  par_quartier: { quartier: string; total: number }[];
  conformite_inpdp: {
    photos_floutees: number;
    total_zones_floutees: number;
  };
  taux_resolution_pourcent: number;
}

// =============================================================================
// Module Simulateur de Trafic Indépendant (Grand Tunis API)
// =============================================================================

export interface TrafficSegment {
  id: string;
  name: string;
  zone: string;
  coordinates: [number, number][];
  base_speed_kmh: number;
  current_speed_kmh: number;
  congestion_level: 'FLUID' | 'MODERATE' | 'HEAVY' | 'BLOCKED';
  congestion_index: number;
  color: string;
  delay_seconds: number;
  vehicle_density: number;
  has_incident: boolean;
  incident_description?: string | null;
}

export interface TrafficSummary {
  average_congestion_index: number;
  global_status: string;
  active_incidents: number;
  average_speed_kmh: number;
  congested_segments_count: number;
  total_segments: number;
  preset_name: string;
  timestamp: string;
  zone_indices: Record<string, number>;
}

export interface RouteDelayResponse {
  distance_km: number;
  free_flow_duration_min: number;
  traffic_duration_min: number;
  delay_minutes: number;
  traffic_status: string;
  impacted_segments: string[];
  congestion_factor: number;
  warning?: string | null;
}

