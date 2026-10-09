/**
 * Committed demo scenario for the Aadesh "Field Instrument" UI.
 *
 * This is the build-time fixture the brief's Part 2 asks for: a single seeded
 * scenario the redesigned /site and /parchi screens render from, so the demo
 * video never waits on a cold API start and the UI is reproducible offline.
 *
 * The live JSON API shape (web/lib/types.ts) is intentionally mirrored here so
 * the same React components can consume either this seed or the real /api
 * response. When the API is up, the "Live corpus" toggle on /site swaps the
 * source; the seeded "Stage III replay" path always uses this fixture.
 *
 * Hindi microcopy is kept short (≤12 words each). Where I am not fully certain
 * a phrasing is natural Hindi rather than translated English, I have flagged it
 * with a REVIEW-HI comment for a native speaker to confirm before submission.
 */

/** One construction site the demo is about. Mirrors types.Site-ish. */
export const DEMO_SITE = {
  site_id: "site-piling-kariana",
  label: "Kariana Piling — Sector 52, Noida",
  activity_type: "Piling works.",
  project_category: "Residential building",
} as const;

/** The officially invoked stage for the seeded scenario. */
export const DEMO_OFFICIAL_STAGE = {
  stage: 3,
  invoked_at: "2026-10-09T06:45:00+05:30",
  lifecycle: "active" as const,
  order_doc_id: "CAQM-GRAP-Order-16Oct2026-5838a44f",
  order_date: "2026-10-09",
  order_short_hash: "5838a44f",
  citation: {
    source_doc: "CAQM Order dated 220120265838a44f",
    source_page: 3,
    source_quote:
      "Construction work including excavation, piling and civil construction activities in identified areas shall be stopped during the period of invocation of Stage III.",
    source_hash: "a3f91c2e7b9d4f1e8c6a2b5d3f9e1c7a4b8d2f6e5c1a9b3d7f4e2c8a6b0d4f1e",
  },
} as const;

/** The nearest station reading for the seeded scenario. */
export const DEMO_READING = {
  station_id: "Rohini",
  parameter: "aqi",
  value: 412,
  observed_at: "2026-10-09T09:00:00+05:30",
  ingested_at: "2026-10-09T09:05:00+05:30",
  provenance: "measured" as const,
  freshness: "FRESH" as const,
  age_minutes: 18,
} as const;

/** The AQI-implied stage, so the discrepancy line has something to say. */
export const DEMO_IMPLIED_STAGE = 3 as const;

/** A single obligation the seeded scenario surfaces for this site. */
export const DEMO_OBLIGATION = {
  obligation_id: "GRAP-III-3.2-dust",
  label: "Stop dust-generating construction activity",
  mode: "regulatory",
  applicable: true,
  status: "NOT_MET" as const,
  required_action:
    "Cease piling, excavation and any activity that raises dust in the identified area until the invocation lapses.",
  reason:
    "Stage III is invoked for the site's area. The activity list in the order names piling explicitly, and the site is piling works in progress.",
  source_doc: "CAQM Order dated 220120265838a44f",
  source_page: 3,
  source_quote:
    "Construction work including excavation, piling and civil construction activities in identified areas shall be stopped during the period of invocation of Stage III.",
  source_hash:
    "a3f91c2e7b9d4f1e8c6a2b5d3f9e1c7a4b8d2f6e5c1a9b3d7f4e2c8a6b0d4f1e",
  evidence: [
    {
      source_doc: "CAQM Order dated 220120265838a44f",
      source_page: 3,
      source_quote:
        "Construction work including excavation, piling and civil construction activities in identified areas shall be stopped during the period of invocation of Stage III.",
      source_hash:
        "a3f91c2e7b9d4f1e8c6a2b5d3f9e1c7a4b8d2f6e5c1a9b3d7f4e2c8a6b0d4f1e",
    },
  ],
  issues_parchi: true,
} as const;

/** A second, out-of-scope obligation, so the console can show "not applicable" honestly. */
export const DEMO_OBLIGATION_OUT_OF_SCOPE = {
  obligation_id: "GRAP-III-5.1-burn",
  label: "Stop open burning of garbage and biomass",
  mode: "regulatory",
  applicable: false,
  status: "NOT_APPLICABLE" as const,
  required_action:
    "Not required at this site. Open burning is not part of the site's activity profile.",
  reason:
    "The site's activity is piling works. The obligation applies to sites that burn waste; this site does not.",
  source_doc: "CAQM Order dated 220120265838a44f",
  source_page: 5,
  source_quote:
    "Burning of garbage and biomass in identified areas shall be stopped during the period of invocation.",
  source_hash: "b7c1d2e3f4a59687b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  evidence: [],
  issues_parchi: false,
} as const;

/** The Standing Order the supervisor can arm in the seeded scenario. */
export const DEMO_STANDING_ORDER = {
  standing_order_id: "SO-site-piling-kariana-2026-10-09-001",
  site_id: DEMO_SITE.site_id,
  supervisor_id: "supervisor-001",
  trigger: {
    stage: 3,
    match: "Stage III invoked for the site's NCR area",
    type: "stage_invocation",
  },
  actions: [
    { action: "halt_dust_activity", parameters: { activity: "piling" } },
    { action: "issue_parchi", parameters: { per_worker: true } },
  ],
  valid_from: "2026-10-09T09:10:00+05:30",
  valid_until: "2026-10-10T06:45:00+05:30",
  status: "active",
  projected_status: "active",
  created_at: "2026-10-09T09:10:00+05:30",
  signed_at: "2026-10-09T09:10:00+05:30",
  commitment_hash:
    "e9c2a4f17b8d3650c9e24a6b8d1f37e50c92a47b6e8d1f30c5a7b9d2e4f6a8c0",
  trigger_fingerprint:
    "fp-3-5838a44f-2026-10-09T06:45:00+05:30",
} as const;

/** 34 rostered workers for the seeded scenario — the demo climax. */
export const DEMO_WORKERS = [
  { worker_id: "worker-001", display_name: "Ramesh Kumar", registered: true, parchi_id: "PCH-2026-1011-0001", state: "acknowledged" as const },
  { worker_id: "worker-002", display_name: "Suresh Yadav", registered: true, parchi_id: "PCH-2026-1011-0002", state: "acknowledged" as const },
  { worker_id: "worker-003", display_name: "Mohammad Iqbal", registered: true, parchi_id: "PCH-2026-1011-0003", state: "acknowledged" as const },
  { worker_id: "worker-004", display_name: "Pradeep Singh", registered: true, parchi_id: "PCH-2026-1011-0004", state: "acknowledged" as const },
  { worker_id: "worker-005", display_name: "Anil Chauhan", registered: true, parchi_id: "PCH-2026-1011-0005", state: "acknowledged" as const },
  { worker_id: "worker-006", display_name: "Devendra Prasad", registered: true, parchi_id: "PCH-2026-1011-0006", state: "acknowledged" as const },
  { worker_id: "worker-007", display_name: "Naresh Mistri", registered: true, parchi_id: "PCH-2026-1011-0007", state: "acknowledged" as const },
  { worker_id: "worker-008", display_name: "Babulal Gupta", registered: true, parchi_id: "PCH-2026-1011-0008", state: "acknowledged" as const },
  { worker_id: "worker-009", display_name: "Om Prakash", registered: true, parchi_id: "PCH-2026-1011-0009", state: "acknowledged" as const },
  { worker_id: "worker-010", display_name: "Ravi Kumar", registered: true, parchi_id: "PCH-2026-1011-0010", state: "acknowledged" as const },
  { worker_id: "worker-011", display_name: "Sanjay Paswan", registered: true, parchi_id: "PCH-2026-1011-0011", state: "acknowledged" as const },
  { worker_id: "worker-012", display_name: "Hari Om", registered: true, parchi_id: "PCH-2026-1011-0012", state: "acknowledged" as const },
  { worker_id: "worker-013", display_name: "Manoj Kurmi", registered: true, parchi_id: "PCH-2026-1011-0013", state: "acknowledged" as const },
  { worker_id: "worker-014", display_name: "Pramod Sahani", registered: true, parchi_id: "PCH-2026-1011-0014", state: "acknowledged" as const },
  { worker_id: "worker-015", display_name: "Ashok Kumar", registered: true, parchi_id: "PCH-2026-1011-0015", state: "acknowledged" as const },
  { worker_id: "worker-016", display_name: "Bablu Kumar", registered: true, parchi_id: "PCH-2026-1011-0016", state: "acknowledged" as const },
  { worker_id: "worker-017", display_name: "Mahesh Chaudhary", registered: true, parchi_id: "PCH-2026-1011-0017", state: "acknowledged" as const },
  { worker_id: "worker-018", display_name: "Jagdish Mandal", registered: true, parchi_id: "PCH-2026-1011-0018", state: "acknowledged" as const },
  { worker_id: "worker-019", display_name: "Dinesh Rai", registered: true, parchi_id: "PCH-2026-1011-0019", state: "acknowledged" as const },
  { worker_id: "worker-020", display_name: "Sitaram Netam", registered: true, parchi_id: "PCH-2026-1011-0020", state: "acknowledged" as const },
  { worker_id: "worker-021", display_name: "Ganesh Pandey", registered: true, parchi_id: "PCH-2026-1011-0021", state: "acknowledged" as const },
  { worker_id: "worker-022", display_name: "Vijay Gupta", registered: true, parchi_id: "PCH-2026-1011-0022", state: "acknowledged" as const },
  { worker_id: "worker-023", display_name: "Kamleshwar Patel", registered: true, parchi_id: "PCH-2026-1011-0023", state: "acknowledged" as const },
  { worker_id: "worker-024", display_name: "Prakash Bairwa", registered: true, parchi_id: "PCH-2026-1011-0024", state: "acknowledged" as const },
  { worker_id: "worker-025", display_name: "Ramesh Patel", registered: true, parchi_id: "PCH-2026-1011-0025", state: "acknowledged" as const },
  { worker_id: "worker-026", display_name: "Shyam Lal", registered: true, parchi_id: "PCH-2026-1011-0026", state: "acknowledged" as const },
  { worker_id: "worker-027", display_name: "Mohan Rao", registered: true, parchi_id: "PCH-2026-1011-0027", state: "acknowledged" as const },
  { worker_id: "worker-028", display_name: "Lalchand Gor", registered: true, parchi_id: "PCH-2026-1011-0028", state: "acknowledged" as const },
  { worker_id: "worker-029", display_name: "Bhagwan Das", registered: true, parchi_id: "PCH-2026-1011-0029", state: "acknowledged" as const },
  { worker_id: "worker-030", display_name: "Durga Prasad", registered: true, parchi_id: "PCH-2026-1011-0030", state: "acknowledged" as const },
  { worker_id: "worker-031", display_name: "Krishan Kumar", registered: true, parchi_id: "PCH-2026-1011-0031", state: "pending_ack" as const },
  { worker_id: "worker-032", display_name: "Suresh Maravi", registered: true, parchi_id: "PCH-2026-1011-0032", state: "pending_ack" as const },
  { worker_id: "worker-033", display_name: "Arjun Kushwaha", registered: true, parchi_id: "PCH-2026-1011-0033", state: "pending_ack" as const },
  { worker_id: "worker-034", display_name: "Upendra Kumar", registered: false, parchi_id: "PCH-2026-1011-0034", state: "pending_ack" as const },
] as const;

/** The full seeded supervisor payload, shaped like types.SupervisorPayload. */
export const DEMO_SUPERVISOR_PAYLOAD = {
  site_id: DEMO_SITE.site_id,
  entity_type: "construction_site",
  mode: "REPLAY" as const,
  resolved_at: "2026-10-09T09:12:00+05:30",
  official_stage: DEMO_OFFICIAL_STAGE.stage,
  current_official_stage: DEMO_OFFICIAL_STAGE.stage,
  implied_stage: DEMO_IMPLIED_STAGE,
  stage_status: "DISCREPANCY" as const,
  stage_reason:
    "The AQI at Rohini (412) and the official invocation both point to Stage III, but the official invocation is the legal trigger — obligations are evaluated against the order, not the reading. This is the aligned case shown with a discrepancy note so the provenance line is honest about what each signal says.",
  official_invocation: DEMO_OFFICIAL_STAGE,
  implied_stage_citation: {
    source_doc: "Rohini station AQI — 412 at 09:00 IST",
    source_page: 1,
    source_quote: "Rohini station reported AQI 412 at 09:00 IST, which crosses the Stage III AQI threshold.",
    source_hash: "c1d2e3f4a59687b8c9d0e1f2a3b4c5d6e7f8a9b0",
  },
  replay_notice:
    "REPLAY — recorded readings. This is a historical scenario, not a live station feed.",
  reading: DEMO_READING,
  summary: { applicable: 1, out_of_scope: 1, parchi_issuing: 1 },
  fully_sourced: true,
  obligations: [DEMO_OBLIGATION, DEMO_OBLIGATION_OUT_OF_SCOPE],
  excluded_obligations: [],
  site: {
    site_id: DEMO_SITE.site_id,
    label: DEMO_SITE.label,
    activity_type: DEMO_SITE.activity_type,
    project_category: DEMO_SITE.project_category,
  },
  stage_detail: {
    official_stage: DEMO_OFFICIAL_STAGE.stage,
    is_replay: true,
    lifecycle: "active",
    order_doc_id: DEMO_OFFICIAL_STAGE.order_doc_id,
    order_date: DEMO_OFFICIAL_STAGE.order_date,
    order_short_hash: DEMO_OFFICIAL_STAGE.order_short_hash,
    revoked_at: null,
    discrepancy: true,
  },
  standing_order: null as null,
  impact: {
    affected: 34,
    documented: 34,
    acknowledged: 30,
    sealed: 0,
    readiness_ready: 30,
    readiness_total: 34,
    standings: DEMO_WORKERS.map((w) => ({
      worker_id: w.worker_id,
      display_name: w.display_name,
      registered: w.registered,
      parchi_id: w.parchi_id,
      state: w.state,
      has_qr: true,
    })),
  },
} as const;

/** One worker's parchi view, shaped like types.WorkerView, for the seeded scenario. */
export const DEMO_PARCHI_VIEW = {
  status: "PENDING_ACK",
  parchi_id: "PCH-2026-1011-0007",
  site_id: DEMO_SITE.site_id,
  worker_id: "worker-007",
  state: "pending_ack",
  stage: 3,
  provenance: "measured",
  cites_measured_data: true,
  obligation_ids: ["GRAP-III-3.2-dust"],
  readiness_checklist: [
    "Registration number on the site register",
    "Bank account details on file with the contractor",
    "This parchi acknowledged in your own name",
  ],
  expires_at: "2026-10-10T06:45:00+05:30",
} as const;

/**
 * Hindi microcopy for the parchi. Each string is short on purpose. Where I have
 * flagged REVIEW-HI, a native speaker should confirm the phrasing before
 * submission — I have aimed for natural Hindi over translated English, but I am
 * not a Hindi speaker and would rather flag than guess.
 */
export const PARCHI_HI = {
  title: "आज काम बंद है।",
  // REVIEW-HI: is "आपके नाम पर" the right way to say "recorded in your own name"?
  sub: "यह आपकी पर्ची है। इसे स्वीकार करें ताकि रोक आपके नाम पर दर्ज हो।",
  date: "दिनांक",
  site: "स्थल",
  reason: "कारण",
  clause: "लागू धारा",
  checklist: "दस्तावेज़ जाँच-सूची",
  acknowledge: "पर्ची स्वीकार करें",
  ackedTitle: "पर्ची स्वीकार कर ली गई।",
  ackedSub: "दर्ज समय",
  pending: "स्वीकृति प्रतीक्षित",
  sealed: "सीलबंद",
  // REVIEW-HI: does "आज GRAP के तहत काम बंद है" read as natural, or stiff?
  reasonBody: (stage: string) =>
    `आज GRAP ${stage} के तहत काम बंद है।`,
} as const;

export const PARCHI_EN = {
  title: "Work stopped today.",
  sub: "This is your parchi. Confirm it so the halt is recorded in your own name.",
  date: "Date",
  site: "Site",
  reason: "Reason",
  clause: "Applicable clause",
  checklist: "Documentation checklist",
  acknowledge: "Acknowledge parchi",
  ackedTitle: "Parchi acknowledged.",
  ackedSub: "Recorded at",
  pending: "Awaiting your confirmation",
  sealed: "Sealed",
  reasonBody: (stage: string) =>
    `Work stopped today under GRAP ${stage}.`,
} as const;
