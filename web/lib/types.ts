export type Citation = {
  source_doc: string;
  source_page: number;
  source_quote: string;
  source_hash: string | null;
  short_hash?: string;
};

export type ObligationStatus = "MET" | "NOT_MET" | "UNKNOWN" | "NOT_APPLICABLE";

export type Obligation = {
  obligation_id: string;
  label: string;
  mode: string;
  applicable: boolean | null;
  status: ObligationStatus;
  required_action: string;
  reason: string;
  source_doc: string;
  source_page: number;
  source_quote: string;
  source_hash: string | null;
  evidence: (Citation | null)[];
  issues_parchi: boolean;
};

export type InvokedStage = {
  stage: number;
  invoked_at: string;
  lifecycle: "active" | "revoked";
  citation: Citation | null;
  revoked_at: string | null;
  revocation_citation: Citation | null;
};

export type Reading = {
  station_id: string;
  parameter: string;
  value: number;
  observed_at: string;
  ingested_at: string;
  provenance: "measured" | "synthetic" | "replay";
  age_minutes?: number;
  freshness?: "FRESH" | "STALE";
};

export type StageDetail = {
  official_stage: number | "NONE";
  is_replay: boolean;
  lifecycle: "active" | "revoked" | null;
  order_doc_id: string | null;
  order_date: string | null;
  order_short_hash: string | null;
  revoked_at: string | null;
  discrepancy: boolean;
};

export type Impact = {
  affected: number;
  documented: number;
  acknowledged: number;
  sealed: number;
  readiness_ready: number;
  readiness_total: number;
  standings: WorkerStanding[];
};

export type WorkerStanding = {
  worker_id: string;
  display_name: string;
  registered: boolean;
  parchi_id: string | null;
  state: string | null;
  has_qr: boolean;
};

export type StandingOrder = {
  standing_order_id: string;
  site_id: string;
  supervisor_id: string;
  trigger: { stage: number; match: string; type: string };
  actions: { action: string; parameters: Record<string, unknown> }[];
  valid_from: string;
  valid_until: string;
  status: string;
  projected_status: string;
  created_at: string;
  signed_at: string | null;
  commitment_hash: string | null;
  trigger_fingerprint: string | null;
};

export type SupervisorPayload = {
  site_id: string;
  entity_type: string;
  mode: "CURRENT" | "REPLAY";
  resolved_at: string;
  official_stage: number | "NONE";
  current_official_stage: number | "NONE";
  implied_stage: number | null;
  stage_status: "ALIGNED" | "DISCREPANCY" | "OFFICIAL_ONLY" | "NO_OFFICIAL_INVOCATION";
  stage_reason: string;
  official_invocation: InvokedStage | null;
  implied_stage_citation: Citation | null;
  replay_notice: string | null;
  reading: Reading | null;
  summary: Record<string, number>;
  fully_sourced: boolean;
  obligations: Obligation[];
  excluded_obligations: { obligation_id: string; reason: string }[];
  site: {
    site_id: string;
    label: string;
    activity_type: string | null;
    project_category: string | null;
  };
  stage_detail: StageDetail;
  standing_order: StandingOrder | null;
  impact: Impact;
};

export type WorkerView = {
  status: string;
  parchi_id: string;
  site_id: string;
  worker_id: string;
  state: string;
  stage: number | null;
  provenance?: "measured" | "synthetic" | "replay" | null;
  cites_measured_data?: boolean;
  obligation_ids?: string[];
  entitlement_refs?: string[];
  readiness_checklist?: string[];
  displaced_worker_days?: number;
  source_document_ids?: string[];
  source_hashes?: string[];
  expires_at?: string;
  acknowledged_at?: string | null;
  sealed_at?: string | null;
  content_hash?: string | null;
};

export type CedarDecision = {
  attempted: string;
  allowed: boolean;
  policy_id: string | null;
  reason: string;
};

export type FacilitatorPayload = {
  worker_id?: string;
  parchi_id?: string;
  error?: string;
  assistance?: CedarDecision & {
    view?: {
      context_id: string;
      parchi_id: string;
      worker_id: string;
      site_id: string;
      claim_status: string;
      consent_status: string;
      consent_granted_at: string;
      consent_expires_at: string;
    };
  };
  read_attempt?: CedarDecision;
  ungranted_consent_attempt?: CedarDecision;
};

export type VerifyPayload = {
  verify: { command: string; exit_code: number; passed: boolean; output: string };
  tamper: { command: string; exit_code: number; caught: boolean; output: string };
};

export type PublicInvocation = {
  stage: number;
  invoked_at: string;
  order_doc_id: string;
  order_sha256: string;
  lifecycle: "active" | "revoked";
  revoked_at: string | null;
  is_current: boolean;
  describe: string;
};

export type PublicReading = {
  station_id: string;
  parameter: string;
  value: number;
  observed_at: string;
  provenance: string;
  is_synthetic: boolean;
  is_measured: boolean;
  is_replay: boolean;
};

export type PublicMetric = {
  count: number;
  label: string;
  description: string;
  status: "live" | "demo" | "synthetic" | "historical" | "unavailable";
  status_reason: string;
  reporting_period: string | null;
};

export type PublicImpactPayload = {
  mode: "CURRENT" | "REPLAY";
  is_replay: boolean;
  is_current_invocation: boolean;
  invocation: PublicInvocation | null;
  reading: PublicReading | null;
  metrics: {
    sites_with_active_standing_orders: PublicMetric;
    sites_acknowledging_regulated_halts: PublicMetric;
    dust_activities_halted: PublicMetric;
    workers_with_documented_displacement: PublicMetric;
  };
  data_note: string;
  claim_boundary: string;
};
