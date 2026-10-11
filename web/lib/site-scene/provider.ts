import { SITE_SCENE_FIXTURES } from "./configs.ts";
import { assembleSiteScene, validateSiteSceneConfig } from "./assemble.ts";
import type { SiteSceneConfig } from "./types.ts";

export type SiteSceneConfigurationRequest = { configurationId: string };

/**
 * Provider seam for an explicitly requested scene configuration update.
 * A model-backed implementation must be a backend adapter; never put AWS credentials here.
 */
export interface SiteSceneConfigurationProvider {
  propose(request: SiteSceneConfigurationRequest): Promise<unknown>;
}

/** Offline baseline: returns only a checked fixture; no model call or network request. */
export const deterministicSiteSceneProvider: SiteSceneConfigurationProvider = {
  async propose({ configurationId }) {
    const fixture = SITE_SCENE_FIXTURES.find((item) => item.id === configurationId);
    if (!fixture) throw new Error("Unknown illustrative site layout.");
    return structuredClone(fixture);
  },
};

/** Treat any remote/provider response as untrusted JSON and validate before assembly. */
export function validateSceneProposal(value: unknown): SiteSceneConfig {
  const record = asRecord(value, "scene proposal");
  exactKeys(record, ["schemaVersion", "id", "title", "provenance", "units", "boundary", "building", "components", "siteFeatures", "zones"], "scene proposal");
  const boundary = asRecord(record.boundary, "boundary");
  exactKeys(boundary, ["width", "depth"], "boundary");
  const building = asRecord(record.building, "building");
  exactKeys(building, ["footprint", "bays", "floors", "floorHeight", "phase"], "building");
  const footprint = asRecord(building.footprint, "building footprint");
  exactKeys(footprint, ["width", "depth"], "building footprint");
  const bays = asRecord(building.bays, "building bays");
  exactKeys(bays, ["x", "z"], "building bays");
  const components = asRecord(record.components, "components");
  exactKeys(components, ["floors", "columns", "walls", "scaffolding"], "components");
  const siteFeatures = asRecord(record.siteFeatures, "site features");
  exactKeys(siteFeatures, ["perimeterFence", "equipment", "crane", "roads"], "site features");
  if (!Array.isArray(record.zones)) throw new Error("Scene proposal zones must be an array.");
  for (const [index, rawZone] of record.zones.entries()) {
    const zone = asRecord(rawZone, `zone ${index + 1}`);
    exactKeys(zone, ["id", "label", "center", "size"], `zone ${index + 1}`);
    if (!Array.isArray(zone.center) || zone.center.length !== 2 || !zone.center.every(isFiniteNumber)) throw new Error(`Zone ${index + 1} needs a two-dimensional center.`);
    if (!Array.isArray(zone.size) || zone.size.length !== 2 || !zone.size.every(isFiniteNumber)) throw new Error(`Zone ${index + 1} needs a two-dimensional size.`);
    if (typeof zone.id !== "string" || typeof zone.label !== "string") throw new Error(`Zone ${index + 1} needs a string id and label.`);
  }
  if (!isFiniteNumber(record.schemaVersion) || typeof record.id !== "string" || typeof record.title !== "string" || typeof record.provenance !== "string" || record.units !== "meters") throw new Error("Scene proposal metadata has invalid types.");
  for (const [name, object] of [["boundary", boundary], ["footprint", footprint], ["bays", bays]] as const) {
    for (const [key, child] of Object.entries(object)) if (!isFiniteNumber(child)) throw new Error(`${name}.${key} must be a finite number.`);
  }
  if (!isFiniteNumber(building.floors) || !isFiniteNumber(building.floorHeight) || typeof building.phase !== "string") throw new Error("Building geometry has invalid types.");
  for (const [name, object] of [["components", components], ["siteFeatures", siteFeatures]] as const) {
    for (const [key, child] of Object.entries(object)) if (typeof child !== "boolean") throw new Error(`${name}.${key} must be a boolean.`);
  }
  const config = value as SiteSceneConfig;
  const errors = validateSiteSceneConfig(config);
  if (errors.length) throw new Error(`Scene proposal rejected: ${errors.join(" ")}`);
  // Assembly also checks the generated placement budget and the registry identifiers used by the engine.
  assembleSiteScene(config);
  return config;
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be an object.`);
  return value as Record<string, unknown>;
}

function exactKeys(record: Record<string, unknown>, allowed: string[], label: string) {
  const keys = Object.keys(record);
  const extra = keys.filter((key) => !allowed.includes(key));
  const missing = allowed.filter((key) => !(key in record));
  if (extra.length || missing.length) throw new Error(`${label} fields are invalid${extra.length ? `; unknown: ${extra.join(", ")}` : ""}${missing.length ? `; missing: ${missing.join(", ")}` : ""}.`);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
