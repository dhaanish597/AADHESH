import type { SupervisorPayload, Obligation } from '@/lib/types';
import type { SiteElement } from './types';

/**
 * Normalizes element IDs so legacy supervisor keys and 3D scene IDs
 * interoperate seamlessly.
 */
export function canonicalElementId(id: string): string {
  const map: Record<string, string> = {
    'activity-zone': 'zone-piling',
    'dust-zone': 'zone-dust',
    'restricted-area': 'zone-demolition',
    'worker-point': 'zone-worker',
    'evidence-station': 'zone-evidence',
    terminal: 'building-main',
  };
  return map[id] ?? id;
}

/**
 * Maps a 3D element ID back to the supervisor workspace SceneObjectKey
 * if applicable, or returns the canonical 3D ID.
 */
export function toSupervisorObjectKey(id: string): string {
  const reverseMap: Record<string, string> = {
    'zone-piling': 'activity-zone',
    'zone-dust': 'dust-zone',
    'zone-demolition': 'restricted-area',
    'zone-worker': 'worker-point',
    'zone-evidence': 'evidence-station',
    'building-main': 'activity-zone',
  };
  return reverseMap[id] ?? id;
}

/**
 * Resolves live data from SupervisorPayload into a typed map of 3D SiteElements.
 * If payload is null, returns honest fallback structures with clear [DEMO / OFFLINE] markings.
 */
export function resolveSiteElements(payload: SupervisorPayload | null): Map<string, SiteElement> {
  const elements = new Map<string, SiteElement>();

  // Extract obligations
  const obligations: Obligation[] = payload?.obligations ?? [];
  const dustObligation =
    obligations.find(
      (o) =>
        o.label.toLowerCase().includes('dust') ||
        o.label.toLowerCase().includes('smog') ||
        o.label.toLowerCase().includes('water') ||
        o.obligation_id.includes('dust-mitigation'),
    ) ?? null;

  const pilingObligation =
    obligations.find(
      (o) =>
        o.obligation_id.includes('piling') ||
        o.label.toLowerCase().includes('piling'),
    ) ?? null;

  const demolitionObligation =
    obligations.find(
      (o) =>
        o.obligation_id.includes('demolition') ||
        o.label.toLowerCase().includes('demolition'),
    ) ?? null;

  const registrationObligation =
    obligations.find(
      (o) =>
        o.obligation_id.includes('registration') ||
        o.obligation_id.includes('large-project'),
    ) ?? null;

  const officialStage = payload?.official_stage ?? 'NONE';
  const stageNum = typeof officialStage === 'number' ? officialStage : 0;
  const isStage3Active = stageNum >= 3;

  const reading = payload?.reading ?? null;
  const impact = payload?.impact ?? null;
  const awaitingParchis = impact ? impact.documented - impact.acknowledged : 0;
  const isFresh = reading?.freshness === 'FRESH';

  // 1. Main Building
  elements.set('building-main', {
    id: 'building-main',
    type: 'building',
    displayName: payload?.site.label ?? 'Main Tower Block A',
    zoneCategory: 'Superstructure',
    presentationState: payload
      ? registrationObligation?.status === 'MET' || !isStage3Active
        ? 'verified'
        : 'action_required'
      : 'verified',
    description: payload
      ? `Active ${payload.site.project_category ?? 'commercial/residential'} structural frame under ${
          typeof officialStage === 'number' ? `GRAP Stage ${officialStage}` : 'baseline'
        } monitoring. Piling activity: ${payload.site.activity_type ?? 'Piling works'}.`
      : 'Primary 5-story reinforced-concrete frame development in Delhi-NCR.',
    obligation: registrationObligation,
    details: {
      location: 'Sector 4 Central Plot (28.6139° N, 77.2090° E)',
      statusNote: payload
        ? `Stage status: ${payload.stage_status} · Resolved: ${new Date(payload.resolved_at).toLocaleTimeString()}`
        : 'Superstructure 68% complete under verified dust-mitigation mandate',
      equipmentCount: 12,
      lastInspection: payload ? 'Verified against CAQM Corpus' : 'Verified this morning',
    },
    coordinates: [0, 10, 0],
    isDemoMetric: !payload,
  });

  // 2. Building Floor Slabs L0..L4
  const floorData = [
    {
      level: 0,
      name: 'Ground Floor Slab & Perimeter',
      desc: 'Ground slab, boundary paving, wheel-wash transition bath, and foundation perimeter.',
      state: 'verified' as const,
      elevation: '+0.0m',
      statusNote: 'Perimeter paving intact; anti-dust boundary barriers active',
    },
    {
      level: 1,
      name: 'Level 1 Commercial Deck',
      desc: 'First commercial tier. Formwork stripping completed; structural columns curing under wet burlap.',
      state: 'verified' as const,
      elevation: '+4.2m',
      statusNote: 'Column curing active with non-potable water misting',
    },
    {
      level: 2,
      name: 'Level 2 Intermediate Slab',
      desc: 'Intermediate deck. Masonry block work staging; perimeter debris containment nets secured.',
      state: 'verified' as const,
      elevation: '+8.4m',
      statusNote: 'Safety nets verified; no dry block cutting allowed on open deck',
    },
    {
      level: 3,
      name: 'Level 3 Upper Shell Deck',
      desc: 'Upper shell level. Formwork erection in progress; boundary dust-suppression mist nozzles active.',
      state: isFresh ? ('verified' as const) : ('stale' as const),
      elevation: '+12.6m',
      statusNote: isFresh ? 'Mist nozzles verified at 2.8 bar' : 'Misting log telemetry stale (>4h)',
    },
    {
      level: 4,
      name: 'Level 4 Active Top Deck',
      desc: 'Top active structural deck. Active concrete pour and reinforcement cage fixing; wind monitoring active.',
      state: isStage3Active ? ('action_required' as const) : ('verified' as const),
      elevation: '+16.8m',
      statusNote: isStage3Active
        ? 'Restricted activity review in effect under GRAP Stage III'
        : 'Active concrete pour and curing stage',
    },
  ];

  for (const f of floorData) {
    elements.set(`floor-${f.level}`, {
      id: `floor-${f.level}`,
      type: 'floor',
      displayName: f.name,
      floorIdentifier: `L${f.level}`,
      zoneCategory: 'Structure',
      presentationState: f.state,
      description: f.desc,
      obligation: dustObligation,
      details: {
        location: `Tower Block A - Elevation ${f.elevation}`,
        statusNote: f.statusNote,
        equipmentCount: f.level >= 3 ? 4 : 2,
        lastInspection: payload ? 'Synced via operations resolver' : 'Today, 07:45 IST',
      },
      coordinates: [0, f.level * 4.2 + 2, 0],
      isDemoMetric: !payload,
    });
  }

  // 3. Tower Crane
  elements.set('crane-tower-1', {
    id: 'crane-tower-1',
    type: 'crane',
    displayName: 'Tower Crane TC-01',
    zoneCategory: 'Lifting Equipment',
    presentationState: isStage3Active ? 'action_required' : 'verified',
    description:
      'Luffing tower crane with ultrasonic anemometer telemetry. Operations governed by statutory high-wind & particulate suppression protocols.',
    details: {
      location: 'North-East Core Berth (Elevation +42m)',
      statusNote:
        'Ultrasonic wind speed 14 km/h (< 38 km/h limit); anti-collision & anti-smog interlock engaged',
      equipmentCount: 1,
      lastInspection: 'Daily pre-lift log approved 07:00 IST',
    },
    coordinates: [-18, 26, -16],
    isDemoMetric: !payload,
  });

  // 4. Piling & Foundation Sector (zone-piling)
  const pilingState = isStage3Active ? 'action_required' : 'verified';
  elements.set('zone-piling', {
    id: 'zone-piling',
    type: 'zone',
    displayName: 'Piling & Foundation Sector',
    zoneCategory: 'Foundation Drilling',
    presentationState: pilingState,
    description: isStage3Active
      ? 'Bored cast-in-situ piling zone. Prohibited across NCR under CAQM Stage III C&D restrictions.'
      : 'Active bored cast-in-situ piling zone with slurry management and vibration monitoring.',
    obligation: pilingObligation,
    details: {
      location: 'East Boundary Grid E3-G5',
      statusNote: isStage3Active
        ? 'Stage III condition: Piling activity restricted. Work must halt or transition to non-restricted tier.'
        : 'Slurry settlement tank sealed; acoustic curtains deployed',
      equipmentCount: 2,
      lastInspection: payload ? 'Resolved via official corpus citation' : '08:15 IST by Site Engineer',
    },
    coordinates: [24, 2, -14],
    isDemoMetric: !payload,
  });

  // 5. Demolition & Crushing Bay (zone-demolition)
  elements.set('zone-demolition', {
    id: 'zone-demolition',
    type: 'zone',
    displayName: 'Demolition & Crushing Bay',
    zoneCategory: 'Structure Removal',
    presentationState: isStage3Active ? 'action_required' : 'verified',
    description:
      'Debris removal, pneumatic breaking, and concrete crushing bay. Subject to strict wet-suppression and stage restrictions.',
    obligation: demolitionObligation,
    details: {
      location: 'West Perimeter Bay W1',
      statusNote: isStage3Active
        ? 'Restricted under CAQM Stage III: Demolition works restricted across NCR'
        : 'Wet mist spray active on demolition excavator EX-04',
      equipmentCount: 3,
      lastInspection: payload ? 'CAQM Order Verified' : '09:00 IST — Action Ticket #104',
    },
    coordinates: [-24, 2, 2],
    isDemoMetric: !payload,
  });

  // 6. Material Staging & Batching (zone-material)
  elements.set('zone-material', {
    id: 'zone-material',
    type: 'zone',
    displayName: 'Material Staging & Batching',
    zoneCategory: 'Storage & Transport',
    presentationState: reading?.freshness === 'STALE' ? 'stale' : 'verified',
    description:
      'Aggregate stockpiles and bulk cement silos. Tarpaulin covering of materials mandatory under CAQM dust rules.',
    details: {
      location: 'North-West Logistical Bay',
      statusNote:
        reading?.freshness === 'STALE'
          ? 'Evidence timestamp stale (>4 hours since last verified tarpaulin inspection)'
          : 'Stockpiles fully sheeted; moisture sensor reporting adequate humidity',
      equipmentCount: 1,
      lastInspection: reading ? `Station reading age: ${reading.age_minutes ?? 0}m` : 'Yesterday 17:30 IST',
    },
    coordinates: [-22, 2, -20],
    isDemoMetric: !payload,
  });

  // 7. Dust-Generating Work Zone (zone-dust)
  const dustMet = dustObligation?.status === 'MET';
  elements.set('zone-dust', {
    id: 'zone-dust',
    type: 'zone',
    displayName: 'Dust-Generating Work Zone',
    zoneCategory: 'Cutting & Masonry',
    presentationState: dustMet ? 'verified' : 'action_required',
    description:
      'Dry cutting of concrete blocks, tile grinding, and plaster batching. Requires continuous wet dust suppression misting.',
    obligation: dustObligation,
    details: {
      location: 'South-East Enclosure SE-2',
      statusNote: dustMet
        ? 'Dust-suppression water sprinklers & mist curtains active'
        : 'Action required: Enclosure curtains must be deployed and mist nozzles pressurized',
      equipmentCount: 4,
      lastInspection: payload ? 'Obligation status: ' + dustObligation?.status : '09:10 IST — Supervisor flagged',
    },
    coordinates: [22, 2, 18],
    isDemoMetric: !payload,
  });

  // 8. Heavy Vehicle Gate & Wheel Wash (zone-access)
  elements.set('zone-access', {
    id: 'zone-access',
    type: 'zone',
    displayName: 'Heavy Vehicle Gate & Wheel Wash',
    zoneCategory: 'Access Logistics',
    presentationState: 'verified',
    description:
      'Primary vehicle transit corridor. Automated tire-washing bath prevents C&D mud and particulate carryover to public roads.',
    details: {
      location: 'South Main Gate Entry Road',
      statusNote: 'Tire wash bath water recycling unit operational (100% trucks cleaned before exit)',
      equipmentCount: 2,
      lastInspection: '08:45 IST — Gate Log verified',
    },
    coordinates: [0, 2, 30],
    isDemoMetric: !payload,
  });

  // 9. Worker Assembly & Roster Point (zone-worker)
  elements.set('zone-worker', {
    id: 'zone-worker',
    type: 'zone',
    displayName: 'Worker Assembly & Parchi Point',
    zoneCategory: 'Workforce Roster',
    presentationState: awaitingParchis > 0 ? 'action_required' : 'verified',
    description:
      'Worker muster shelter and compliance communication point. Each rostered worker receives a documented Parchi record.',
    impactSummary: impact
      ? {
          affected: impact.affected,
          documented: impact.documented,
          acknowledged: impact.acknowledged,
          awaiting: awaitingParchis,
          readinessReady: impact.readiness_ready,
          readinessTotal: impact.readiness_total,
        }
      : null,
    details: {
      location: 'South-East Shelter B3 (Grid F6)',
      statusNote: impact
        ? `${impact.acknowledged} of ${impact.documented} issued Parchis acknowledged by workers (${awaitingParchis} awaiting)`
        : '34 workers registered on active site roster',
      equipmentCount: impact?.affected ?? 34,
      lastInspection: 'Live workforce sync',
    },
    coordinates: [28, 2, -28],
    isDemoMetric: !payload,
  });

  // 10. Evidence & Environmental Monitoring Station (zone-evidence)
  elements.set('zone-evidence', {
    id: 'zone-evidence',
    type: 'zone',
    displayName: 'Evidence & Air Quality Station',
    zoneCategory: 'Monitoring & Provenance',
    presentationState: reading?.freshness === 'STALE' ? 'stale' : 'verified',
    description:
      'On-site environmental telemetry node and citation provenance terminal. Traces statutory obligations to hashed order bytes.',
    readingSummary: reading
      ? {
          stationId: reading.station_id,
          parameter: reading.parameter,
          value: reading.value,
          provenance: reading.provenance,
          freshness: reading.freshness,
          observedAt: reading.observed_at,
        }
      : null,
    details: {
      location: 'North-West Boundary Mast MW-1',
      statusNote: reading
        ? `${reading.parameter}: ${reading.value} µg/m³ · Provenance: ${reading.provenance} (${reading.freshness ?? 'FRESH'})`
        : 'CPCB Calibrated Optical Particle Counter',
      equipmentCount: 1,
      lastInspection: reading ? `Observed ${new Date(reading.observed_at).toLocaleTimeString()}` : '09:00 IST',
    },
    coordinates: [-30, 2, 22],
    isDemoMetric: !payload,
  });

  // 11. Vehicle: Tipper Truck DL-1M-4820
  elements.set('vehicle-tipper-1', {
    id: 'vehicle-tipper-1',
    type: 'vehicle',
    displayName: 'Tipper Truck DL-1M-4820',
    zoneCategory: 'Material Transport',
    presentationState: 'verified',
    description:
      '10-wheel heavy tipper carrying crushed stone aggregate. Verified tarpaulin fitted and BS-VI green pass verified.',
    details: {
      location: 'Access Corridor South Gate (Grid S1)',
      statusNote: 'BS-VI engine compliance; green entry pass verified; tire wash complete',
      equipmentCount: 1,
      lastInspection: '08:30 IST Gate Log',
    },
    coordinates: [6, 2, 28],
    isDemoMetric: !payload,
  });

  // 12. Vehicle: Hydraulic Excavator EX-04
  elements.set('vehicle-excavator-1', {
    id: 'vehicle-excavator-1',
    type: 'vehicle',
    displayName: 'Hydraulic Excavator EX-04',
    zoneCategory: 'Earthwork & Demolition',
    presentationState: isStage3Active ? 'action_required' : 'verified',
    description:
      'Heavy crawler excavator operating in demolition sector. Wet spray cannon mandatory during boom operations.',
    obligation: demolitionObligation,
    details: {
      location: 'West Demolition Bay W1',
      statusNote: isStage3Active
        ? 'Restricted: Demolition excavation halted under GRAP Stage III'
        : 'Wet spray canon active during boom engagement',
      equipmentCount: 1,
      lastInspection: '07:45 IST Pre-operation log',
    },
    coordinates: [-23, 2, -4],
    isDemoMetric: !payload,
  });

  // 13. Vehicle: Anti-Smog Mist Truck SM-02
  elements.set('vehicle-sprinkler-1', {
    id: 'vehicle-sprinkler-1',
    type: 'vehicle',
    displayName: 'Anti-Smog Mist Truck SM-02',
    zoneCategory: 'Environmental Dust Mitigation',
    presentationState: dustMet ? 'verified' : 'action_required',
    description:
      'Mobile 5000L water tank truck with 360° high-power turbine mist cannon. Active perimeter suppression.',
    obligation: dustObligation,
    details: {
      location: 'Central Perimeter Ring Road (Grid C4)',
      statusNote: 'Tank 85% full (STP treated non-potable water verified; 3.0 bar cannon pressure)',
      equipmentCount: 1,
      lastInspection: '09:00 IST Daily Log',
    },
    coordinates: [20, 2, 8],
    isDemoMetric: !payload,
  });

  return elements;
}
