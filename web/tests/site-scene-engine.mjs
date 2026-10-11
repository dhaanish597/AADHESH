import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { assembleSiteScene, validateSiteSceneConfig } from "../lib/site-scene/assemble.ts";
import { SITE_SCENE_FIXTURES } from "../lib/site-scene/configs.ts";
import { deterministicSiteSceneProvider, validateSceneProposal } from "../lib/site-scene/provider.ts";
import { SCENE_ASSETS } from "../lib/site-scene/registry.ts";

const root = resolve(import.meta.dirname, "../..");
const [small, midrise] = SITE_SCENE_FIXTURES;
const smallScene = assembleSiteScene(small);
const midriseScene = assembleSiteScene(midrise);

assert.equal(SCENE_ASSETS["column"].boundsMeters.max[1], 2.4);
for (const asset of Object.values(SCENE_ASSETS)) {
  assert.ok(existsSync(resolve(root, "web/public", asset.path.slice(1))), `${asset.id} model exists`);
  for (const dependency of asset.dependencies) assert.ok(existsSync(resolve(root, "web/public", dependency.slice(1))), `${asset.id} dependency exists: ${dependency}`);
}

assert.deepEqual(validateSiteSceneConfig(small), []);
assert.deepEqual(validateSiteSceneConfig(midrise), []);
assert.ok(smallScene.entities.length < midriseScene.entities.length);
assert.equal(smallScene.config.building.floors, 3);
assert.equal(midriseScene.entities.filter((entity) => entity.id.startsWith("slab-f6-")).length, 12);
assert.ok(midriseScene.entities.some((entity) => entity.id === "crane-jib"));
assert.ok(midriseScene.entities.some((entity) => entity.id === "zone-work-area"));
assert.ok(midriseScene.entities.every((entity) => entity.layer && Array.isArray(entity.position)));
assert.ok(midriseScene.entities.every((entity) => !("legalStatus" in entity) && !("restriction" in entity)));
assert.equal(small.provenance, "SYNTHETIC_DEMO_GEOMETRY");

const deterministic = await deterministicSiteSceneProvider.propose({ configurationId: midrise.id });
assert.deepEqual(validateSceneProposal(deterministic), midrise);
await assert.rejects(() => deterministicSiteSceneProvider.propose({ configurationId: "unknown" }), /Unknown illustrative/);
assert.throws(() => validateSceneProposal({ ...small, assetId: "unregistered-crane" }), /unknown: assetId/);
assert.throws(() => validateSceneProposal({ ...small, building: { ...small.building, footprint: { width: 100, depth: 12 } } }), /footprint/);
assert.throws(() => validateSceneProposal({ ...small, zones: [{ ...small.zones[0], center: [99, 99] }] }), /outside the site boundary/);
assert.throws(() => validateSceneProposal({ ...small, zones: [{ ...small.zones[0], status: "RESTRICTED" }] }), /unknown: status/);
assert.throws(() => validateSceneProposal({ ...small, boundary: { width: Infinity, depth: 20 } }), /finite number/);
assert.throws(() => validateSceneProposal({ ...small, provenance: "UNAVAILABLE" }), /Unavailable geometry/);

const kenneyLicense = readFileSync(resolve(root, "web/public/models/kenney/LICENSE-building-kit.txt"), "utf8");
assert.match(kenneyLicense, /Creative Commons Zero/i);
console.log(`Site scene engine passed: ${Object.keys(SCENE_ASSETS).length} registered assets, ${smallScene.entities.length}/${midriseScene.entities.length} fixture entities.`);
