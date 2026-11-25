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
  niveau_couleur?: 'vert' | 'orange' | 'rouge';
  facteurs_explicatifs: string[];
}

export interface ZoneRiskMap {
  zone_id: string;
  zone_nom: string;
  type_troncon?: string;
  latitude: number;
  longitude: number;
  score_risque_pourcentage: number;
  niveau_couleur: 'vert' | 'orange' | 'rouge';
  niveau_risk_map: string;
  facteurs_explicatifs: string[];
  details?: {
    accidents_30j: number;
    indice_trafic: number;
    criticite_geometrie: number;
    meteo_pluie: number;
    presence_travaux: number;
  };
}

export interface AuditInterventionItem {
  id: number;
  statut_precedent: string;
  nouveau_statut: string;
  horodatage: string;
  note_intervention: string;
  matricule_intervenant: string;
}

export interface AssistantLLMResponse {
  question: string;
  reponse: string;
  moteur: string;
  contexte_utilise: {
    nb_alertes_actives: number;
    nb_zones_rouges: number;
    horodatage: string;
  };
}

export interface SimulationResult {
  scenario: string;
  description: string;
  alerte_id?: number;
  statut_alerte?: string;
  nb_signalements_concordants?: number;
  nb_signalements_fusionnes?: number;
  alarme_declenchee?: boolean;
  diffusion_temps_reel?: string;
  message: string;
  repartition?: {
    rouges: number;
    oranges: number;
    vertes: number;
  };
  secteurs?: ZoneRiskMap[];
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
  est_mon_signalement?: boolean;
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

export type UserRole = 'CITOYEN' | 'RESPONSABLE_MUNICIPAL' | 'PROTECTION_CIVILE';

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

export interface ZoneHauteDensite {
  zone: string;
  latitude: number;
  longitude: number;
  nb_signalements: number;
  nb_actifs: number;
  nb_critiques_eleves: number;
  score_densite: number;
  categorie_dominante: string;
}

export interface EvolutionTemporellePoint {
  date: string;
  total: number;
  en_attente: number;
  en_cours: number;
  resolus: number;
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
  chantiers_actifs?: number;
  incidents_en_attente?: number;
  details_chantiers?: {
    en_cours: number;
    confirmes: number;
    voirie_active: number;
  };
  zones_haute_densite?: ZoneHauteDensite[];
  heatmap_points?: [number, number, number][];
  evolution_temporelle?: EvolutionTemporellePoint[];
  anomalies_actives_count?: number;
}

export type StatutAnomalie = 'ACTIVE' | 'ACQUITTEE';
export type SeveriteAnomalie = 'MODERE' | 'ELEVEE' | 'CRITIQUE';

export interface AlerteAnomalieItem {
  id: number;
  statut: StatutAnomalie;
  severite: SeveriteAnomalie;
  quartier: string;
  categorie: string;
  score_anomalie: number;
  decision_raw: number;
  nb_signalements: number;
  fenetre_heures: number;
  latitude_centre: number | null;
  longitude_centre: number | null;
  explication: string;
  date_detection: string;
  date_mise_a_jour: string;
  date_acquittement: string | null;
  acquittee_par_username: string | null;
}

export interface AnomaliesListResponse {
  modele: string;
  total_actives: number;
  anomalies: AlerteAnomalieItem[];
}

export interface AnomalieAnalyseResponse {
  message: string;
  nb_detectees: number;
  anomalies: AlerteAnomalieItem[];
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

