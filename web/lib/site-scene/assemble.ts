import { SCENE_ASSETS } from "./registry.ts";
import type { AssembledScene, SceneEntity, SiteSceneConfig } from "./types";

const finite = (n: number) => Number.isFinite(n);

export function validateSiteSceneConfig(config: SiteSceneConfig): string[] {
  const errors: string[] = [];
  const fail = (message: string) => errors.push(message);
  if (config.schemaVersion !== 1 || config.units !== "meters") fail("Unsupported scene schema or units.");
  if (!config.id.trim() || !config.title.trim()) fail("A scene needs an id and title.");
  if (!["VERIFIED_SITE_GEOMETRY", "CONFIGURED_SITE_GEOMETRY", "SYNTHETIC_DEMO_GEOMETRY", "UNAVAILABLE"].includes(config.provenance)) fail("Unknown geometry provenance.");
  if (config.provenance === "UNAVAILABLE") fail("Unavailable geometry cannot be assembled into a site layout.");
  const { width, depth } = config.boundary;
  if (![width, depth].every(finite) || width < 8 || depth < 8 || width > 80 || depth > 80) fail("Boundary dimensions must be 8–80 m.");
  const { footprint, bays, floors, floorHeight, phase } = config.building;
  if (![footprint.width, footprint.depth, bays.x, bays.z, floors, floorHeight].every(finite)) fail("Building dimensions must be finite numbers.");
  if (footprint.width < 4 || footprint.depth < 4 || footprint.width > width - 4 || footprint.depth > depth - 4) fail("Building footprint must fit inside the site with a 2 m setback.");
  if (!Number.isInteger(bays.x) || !Number.isInteger(bays.z) || bays.x < 1 || bays.z < 1 || bays.x > 8 || bays.z > 8) fail("Structural grid must contain 1–8 bays per axis.");
  if (!Number.isInteger(floors) || floors < 1 || floors > 12 || floorHeight < 2 || floorHeight > 4) fail("Floor count or floor height is outside supported limits.");
  if (!["foundation", "frame", "envelope"].includes(phase)) fail("Unsupported construction phase.");
  if (config.zones.length > 24) fail("A scene supports at most 24 named areas.");
  const zoneIds = new Set<string>();
  for (const zone of config.zones) {
    if (!zone.id.trim() || zoneIds.has(zone.id)) fail(`Zone id is empty or duplicated: ${zone.id}`);
    zoneIds.add(zone.id);
    if (![...zone.center, ...zone.size].every(finite) || zone.size.some((n) => n <= 0)) fail(`Invalid geometry for zone ${zone.id}.`);
    if (Math.abs(zone.center[0]) + zone.size[0] / 2 > width / 2 || Math.abs(zone.center[1]) + zone.size[1] / 2 > depth / 2) fail(`Zone ${zone.id} is outside the site boundary.`);
  }
  if (!config.components.floors && !config.components.columns && !config.components.walls && !config.siteFeatures.equipment) fail("The configuration contains no visible structure or equipment.");
  const estimatedComplexity = floors * (
    (config.components.floors ? bays.x * bays.z : 0)
    + (config.components.columns ? (bays.x + 1) * (bays.z + 1) : 0)
    + (config.components.scaffolding ? 4 + 2 * (bays.x + 1) : 0)
    + (config.components.walls && phase === "envelope" ? bays.x : 0)
  ) + 2 * (Math.ceil(width / 4.4) + Math.ceil(depth / 4.4)) + 100;
  if (estimatedComplexity > 650) fail("Scene layout exceeds the mobile-friendly object budget.");
  return errors;
}

export function assembleSiteScene(config: SiteSceneConfig): AssembledScene {
  const errors = validateSiteSceneConfig(config);
  if (errors.length) throw new Error(`Invalid site scene: ${errors.join(" ")}`);
  const entities: SceneEntity[] = [];
  const add = (entity: SceneEntity) => {
    if (entity.assetId && !SCENE_ASSETS[entity.assetId]) throw new Error(`Unknown scene asset: ${entity.assetId}`);
    if ([...entity.position, ...entity.scale, ...entity.rotation].some((n) => !finite(n) || Math.abs(n) > 100)) throw new Error(`Out-of-bounds transform: ${entity.id}`);
    entities.push(entity);
    if (entities.length > 700) throw new Error("Scene object budget exceeds 700 items.");
  };
  const model = (id: string, label: string, assetId: string, layer: SceneEntity["layer"], position: [number, number, number], scale: [number, number, number], rotation: [number, number, number] = [0, 0, 0], floor?: number) =>
    add({ id, label, assetId, layer, position, scale, rotation, selectable: true, ...(floor === undefined ? {} : { floor }) });
  const box = (id: string, label: string, layer: SceneEntity["layer"], position: [number, number, number], size: [number, number, number], color: string, selectable = true, floor?: number) =>
    add({ id, label, layer, primitive: "box", position, scale: size, rotation: [0, 0, 0], color, selectable, ...(floor === undefined ? {} : { floor }) });

  const { width, depth } = config.boundary;
  const { footprint, bays, floors, floorHeight, phase } = config.building;
  box("site-ground", "Illustrative site ground", "boundary", [0, -0.16, 0], [width + 14, 0.3, depth + 12], "#c5d0d2", false);
  box("site-pad", "Configured site boundary", "boundary", [0, 0.015, 0], [width, 0.12, depth], "#d3d9db", false);
  if (config.siteFeatures.roads) {
    const roadColor = "#68747a";
    box("road-north", "Road edge", "roads", [0, 0.04, -depth / 2 - 2], [width + 7, 0.12, 3.3], roadColor, false);
    box("road-south", "Road edge", "roads", [0, 0.04, depth / 2 + 2], [width + 7, 0.12, 3.3], roadColor, false);
    box("road-west", "Road edge", "roads", [-width / 2 - 2, 0.04, 0], [3.3, 0.12, depth + 7], roadColor, false);
    box("road-east", "Road edge", "roads", [width / 2 + 2, 0.04, 0], [3.3, 0.12, depth + 7], roadColor, false);
  }

  const baseX = -footprint.width / 2;
  const baseZ = -footprint.depth / 2;
  const bayX = footprint.width / bays.x;
  const bayZ = footprint.depth / bays.z;
  for (let level = 1; level <= floors; level++) {
    const y = 0.18 + (level - 1) * floorHeight;
    if (config.components.floors && (phase !== "foundation" || level === 1)) {
      for (let x = 0; x < bays.x; x++) for (let z = 0; z < bays.z; z++) {
        model(`slab-f${level}-${x}-${z}`, `Floor ${level} slab · bay ${x + 1}, ${z + 1}`, "floor", "structure", [baseX + bayX * (x + 0.5), y, baseZ + bayZ * (z + 0.5)], [bayX / 2, 1, bayZ / 2], [0, 0, 0], level);
      }
    }
    if (config.components.columns && level <= floors) {
      for (let x = 0; x <= bays.x; x++) for (let z = 0; z <= bays.z; z++) {
        model(`column-f${level}-${x}-${z}`, `Floor ${level} column · grid ${x + 1}, ${z + 1}`, "column", "structure", [baseX + bayX * x, y + floorHeight / 2, baseZ + bayZ * z], [1, floorHeight / 2.4, 1], [0, 0, 0], level);
      }
    }
    if (config.components.walls && phase === "envelope" && level < floors) {
      // Partial far-side infill keeps the upper active edge open in the synthetic shell.
      for (let x = 0; x < bays.x; x++) model(`wall-f${level}-${x}`, `Floor ${level} partial wall · bay ${x + 1}`, "wall", "structure", [baseX + bayX * (x + 0.5), y + floorHeight / 2, baseZ], [floorHeight / 2.4, floorHeight / 2.4, bayX / 2], [0, Math.PI / 2, 0], level);
    }
    if (config.components.scaffolding && level < floors) {
      const railY = 0.2 + level * floorHeight;
      const x0 = baseX - 0.5, x1 = baseX + footprint.width + 0.5, z0 = baseZ - 0.5, z1 = baseZ + footprint.depth + 0.5;
      const xRail = (id: string, pos: [number, number, number], length: number) => add({ id, label: `Scaffold rail · floor ${level}`, primitive: "tube", layer: "scaffolding", position: pos, scale: [0.045, length, 0.045], rotation: [0, 0, Math.PI / 2], color: "#b77745", selectable: true, floor: level });
      const zRail = (id: string, pos: [number, number, number], length: number) => add({ id, label: `Scaffold rail · floor ${level}`, primitive: "tube", layer: "scaffolding", position: pos, scale: [0.045, length, 0.045], rotation: [Math.PI / 2, 0, 0], color: "#b77745", selectable: true, floor: level });
      xRail(`scaffold-x0-f${level}`, [0, railY, z0], footprint.width + 1);
      xRail(`scaffold-x1-f${level}`, [0, railY, z1], footprint.width + 1);
      zRail(`scaffold-z0-f${level}`, [x0, railY, 0], footprint.depth + 1);
      zRail(`scaffold-z1-f${level}`, [x1, railY, 0], footprint.depth + 1);
    }
  }
  if (config.components.scaffolding && floors > 1) {
    const fullHeight = Math.max(floorHeight, (floors - 1) * floorHeight);
    const postY = 0.2 + (floors - 1) * floorHeight / 2;
    const z0 = baseZ - 0.5, z1 = baseZ + footprint.depth + 0.5;
    for (let x = 0; x <= bays.x; x++) for (const z of [z0, z1]) {
      add({ id: `scaffold-post-${x}-${z}`, label: "Scaffold upright", primitive: "tube", layer: "scaffolding", position: [baseX + bayX * x, postY, z], scale: [0.045, fullHeight, 0.045], rotation: [0, 0, 0], color: "#b77745", selectable: true });
    }
  }

  // The crane is an abstract visual assembly because the source library contains no crane asset.
  if (config.siteFeatures.crane) {
    const cx = footprint.width / 2 + 2.2;
    const mastHeight = floors * floorHeight + 3;
    const mastSections = Math.ceil(mastHeight / 2.1);
    const sectionHeight = mastHeight / mastSections;
    for (let i = 0; i < mastSections; i++) {
      const y = 0.18 + (i + 0.5) * sectionHeight;
      box(`crane-mast-${i}`, "Illustrative tower crane mast", "crane", [cx, y, 0], [0.32, sectionHeight, 0.32], "#e9a528");
      for (const side of [-1, 1]) box(`crane-mast-brace-${i}-${side}`, "Illustrative crane lattice brace", "crane", [cx + side * 0.09, y, 0], [0.46, 0.055, 0.055], "#c48620");
    }
    box("crane-jib", "Illustrative tower crane jib", "crane", [cx + 2.8, 0.18 + mastHeight, 0], [7.4, 0.18, 0.2], "#e9a528");
    box("crane-counter-jib", "Illustrative tower crane counter-jib", "crane", [cx - 1.2, 0.18 + mastHeight, 0], [2.2, 0.18, 0.2], "#d28b1a");
    box("crane-cab", "Illustrative crane operator cab", "crane", [cx + 0.25, 0.18 + mastHeight - 0.1, 0], [0.65, 0.55, 0.58], "#f1ca64");
    box("crane-hook-line", "Illustrative crane hoist", "crane", [cx + 5.4, 0.18 + mastHeight - 1.1, 0], [0.035, 1.8, 0.035], "#3c4240");
    for (let i = 0; i < 6; i++) {
      const x = cx + 0.9 + i * 0.85;
      add({ id: `crane-jib-lattice-${i}`, label: "Illustrative crane jib lattice", primitive: "box", layer: "crane", position: [x, 0.18 + mastHeight + (i % 2 ? 0.26 : -0.26), 0], scale: [1.12, 0.055, 0.055], rotation: [0, 0, i % 2 ? -0.42 : 0.42], color: "#c48620", selectable: true });
    }
  }

  if (config.siteFeatures.perimeterFence) {
    const fenceEdge = (edge: "north" | "south" | "east" | "west", length: number, fixed: number, horizontal: boolean) => {
      const segmentLength = 4.4;
      const count = Math.ceil(length / segmentLength);
      for (let i = 0; i < count; i++) {
        const along = -length / 2 + (i + 0.5) * length / count;
        const position: [number, number, number] = horizontal ? [along, 0.08, fixed] : [fixed, 0.08, along];
        model(`fence-${edge}-${i}`, "Perimeter fence segment", "construction-fence", "boundary", position, [1, 1, length / count / 0.375], horizontal ? [0, 0, 0] : [0, Math.PI / 2, 0]);
      }
    };
    fenceEdge("north", width, -depth / 2, true); fenceEdge("south", width, depth / 2, true);
    fenceEdge("east", depth, width / 2, false); fenceEdge("west", depth, -width / 2, false);
  }

  if (config.siteFeatures.equipment) {
    const dumpX = width / 2 - 2.6;
    model("site-dumpster", "Waste container", "dumpster", "equipment", [dumpX, 0.2, -depth / 2 + 2.8], [8, 8, 8], [0, 0.15, 0]);
    for (let i = 0; i < 6; i++) model(`cone-${i}`, "Construction cone", "construction-cone", "equipment", [-width / 2 + 1.8 + i * 1.25, 0.09, depth / 2 - 2], [7, 7, 7]);
    for (let i = 0; i < 3; i++) model(`barrier-${i}`, "Portable construction barrier", "construction-barrier", "equipment", [-width / 2 + 2 + i * 2.1, 0.12, -depth / 2 + 6], [10, 7, 5], [0, Math.PI / 2, 0]);
    for (let i = 0; i < 3; i++) box(`material-stack-${i}`, "Illustrative stored material", "equipment", [baseX - 2.2, 0.38 + i * 0.32, baseZ + 3 + i * 0.45], [2.2, 0.3, 1], "#b78654");
  }

  if (config.siteFeatures.roads) {
    // Low-poly context models are visual surroundings, not neighboring real properties.
    model("context-building-a", "Illustrative surrounding building", "building-a", "roads", [-width / 2 - 4.1, 0.1, -depth / 2 - 3.2], [4.3, 4.3, 4.3]);
    model("context-building-c", "Illustrative surrounding building", "building-c", "roads", [width / 2 + 4, 0.1, depth / 2 + 3.2], [4, 4, 4]);
  }
  for (const zone of config.zones) {
    add({ id: `zone-${zone.id}`, label: zone.label, layer: "zones", primitive: "zone", position: [zone.center[0], 0.105, zone.center[1]], scale: [zone.size[0], 1, zone.size[1]], rotation: [0, 0, 0], color: "#4e9e7a", opacity: 0.3, selectable: true });
  }
  return { config, entities };
}
