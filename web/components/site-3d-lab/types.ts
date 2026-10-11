import type { Obligation, Reading, Impact } from '@/lib/types';

export type ElementType =
  | 'building'
  | 'floor'
  | 'zone'
  | 'crane'
  | 'vehicle'
  | 'infrastructure';

export type PresentationState =
  | 'normal'
  | 'verified'
  | 'action_required'
  | 'stale'
  | 'unknown';

export type CameraPreset =
  | 'overview'
  | 'building'
  | 'crane'
  | 'ground'
  | 'focus-selected';

export interface SiteElementDetails {
  location?: string;
  statusNote?: string;
  equipmentCount?: number;
  lastInspection?: string;
}

export interface SiteElement {
  id: string;
  type: ElementType;
  displayName: string;
  floorIdentifier?: string;
  zoneCategory?: string;
  presentationState?: PresentationState;
  externalReferenceId?: string;
  description?: string;
  details?: SiteElementDetails;
  // Dynamic backend bindings
  obligation?: Obligation | null;
  impactSummary?: {
    affected: number;
    documented: number;
    acknowledged: number;
    awaiting: number;
    readinessReady: number;
    readinessTotal: number;
  } | null;
  readingSummary?: {
    stationId: string;
    parameter: string;
    value: number;
    provenance: string;
    freshness?: string;
    observedAt: string;
  } | null;
  isDemoMetric?: boolean;
  coordinates?: [number, number, number];
}

export type OnElementSelect = (element: SiteElement | null) => void;

