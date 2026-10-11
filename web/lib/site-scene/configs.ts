import type { SiteSceneConfig } from "./types";

/** Synthetic design fixtures: never populated from, or presented as, a live site record. */
export const SITE_SCENE_FIXTURES: SiteSceneConfig[] = [
  {
    schemaVersion: 1,
    id: "demo-small-frame",
    title: "Frame · 3 floors",
    provenance: "SYNTHETIC_DEMO_GEOMETRY",
    units: "meters",
    boundary: { width: 24, depth: 20 },
    building: { footprint: { width: 12, depth: 8 }, bays: { x: 3, z: 2 }, floors: 3, floorHeight: 3.1, phase: "frame" },
    components: { floors: true, columns: true, walls: true, scaffolding: true },
    siteFeatures: { perimeterFence: true, equipment: true, crane: true, roads: true },
    zones: [
      { id: "work-area", label: "Frame work area", center: [0, -6.8], size: [4.8, 3.2] },
      { id: "material-storage", label: "Material staging area", center: [5.4, 4.1], size: [4.6, 3.2] },
      { id: "site-office", label: "Temporary office area", center: [-7.5, 4.1], size: [3.8, 3.1] },
    ],
  },
  {
    schemaVersion: 1,
    id: "demo-midrise-shell",
    title: "Mid-rise shell · 6 floors",
    provenance: "SYNTHETIC_DEMO_GEOMETRY",
    units: "meters",
    boundary: { width: 34, depth: 28 },
    building: { footprint: { width: 18, depth: 12 }, bays: { x: 4, z: 3 }, floors: 6, floorHeight: 3.2, phase: "envelope" },
    components: { floors: true, columns: true, walls: true, scaffolding: true },
    siteFeatures: { perimeterFence: true, equipment: true, crane: true, roads: true },
    zones: [
      { id: "work-area", label: "Frame work area", center: [0, -9.5], size: [5.8, 3.8] },
      { id: "material-storage", label: "Material staging area", center: [7.8, 6.3], size: [5.6, 4.2] },
      { id: "site-office", label: "Temporary office area", center: [-12.1, 6.2], size: [4.4, 3.6] },
    ],
  },
];
