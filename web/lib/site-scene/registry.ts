import type { SceneLayer } from "./types";

export type SceneAsset = {
  id: string;
  path: string;
  purpose: string;
  source: string;
  license: "CC0-1.0";
  boundsMeters: { min: [number, number, number]; max: [number, number, number] };
  dependencies: string[];
  layer: SceneLayer;
  finish?: string;
};

/** Runtime-safe assets selected from the audited Kenney GLB kits. */
export const SCENE_ASSETS: Record<string, SceneAsset> = {
  "building-a": { id: "building-a", path: "/models/kenney/building-a.glb", purpose: "Finished low-rise context building", source: "kenney_city-kit-commercial_2.1.zip / Models/GLB format/building-a.glb", license: "CC0-1.0", boundsMeters: { min: [-0.442, 0, -0.47], max: [0.442, 1.293, 0.47] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "structure" },
  "building-c": { id: "building-c", path: "/models/kenney/building-c.glb", purpose: "Finished low-rise context building", source: "kenney_city-kit-commercial_2.1.zip / Models/GLB format/building-c.glb", license: "CC0-1.0", boundsMeters: { min: [-0.442, 0, -0.545], max: [0.442, 0.893, 0.545] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "structure" },
  column: { id: "column", path: "/models/kenney/column.glb", purpose: "Modular concrete column (0.5 × 2.4 × 0.5 source units)", source: "kenney_building-kit.zip / Models/GLB format/column.glb", license: "CC0-1.0", boundsMeters: { min: [-0.25, 0, -0.25], max: [0.25, 2.4, 0.25] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "structure", finish: "#7e898f" },
  floor: { id: "floor", path: "/models/kenney/floor.glb", purpose: "Modular floor slab (2 × 0.1 × 2 source units)", source: "kenney_building-kit.zip / Models/GLB format/floor.glb", license: "CC0-1.0", boundsMeters: { min: [-1, 0, -1], max: [1, 0.1, 1] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "structure", finish: "#838e94" },
  wall: { id: "wall", path: "/models/kenney/wall.glb", purpose: "Modular wall section (0.1 × 2.4 × 2 source units)", source: "kenney_building-kit.zip / Models/GLB format/wall.glb", license: "CC0-1.0", boundsMeters: { min: [-0.05, 0, -1], max: [0.05, 2.4, 1] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "structure", finish: "#b1b4af" },
  "construction-fence": { id: "construction-fence", path: "/models/kenney/construction-fence.glb", purpose: "Construction perimeter fence segment", source: "kenney_city-kit-roads.zip / Models/GLB format/construction-fence.glb", license: "CC0-1.0", boundsMeters: { min: [-0.038, 0, -0.188], max: [0.038, 0.179, 0.188] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "boundary" },
  "construction-barrier": { id: "construction-barrier", path: "/models/kenney/construction-barrier.glb", purpose: "Portable construction barrier", source: "kenney_city-kit-roads.zip / Models/GLB format/construction-barrier.glb", license: "CC0-1.0", boundsMeters: { min: [-0.068, 0, -0.113], max: [0.068, 0.13, 0.113] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "boundary" },
  "construction-cone": { id: "construction-cone", path: "/models/kenney/construction-cone.glb", purpose: "Traffic/construction cone", source: "kenney_city-kit-roads.zip / Models/GLB format/construction-cone.glb", license: "CC0-1.0", boundsMeters: { min: [-0.038, 0, -0.038], max: [0.038, 0.094, 0.038] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "equipment" },
  dumpster: { id: "dumpster", path: "/models/kenney/dumpster.glb", purpose: "Site waste container", source: "kenney_city-kit-roads.zip / Models/GLB format/dumpster.glb", license: "CC0-1.0", boundsMeters: { min: [-0.13, 0, -0.185], max: [0.145, 0.206, 0.185] }, dependencies: ["/models/kenney/Textures/colormap.png"], layer: "equipment" },
};

export const SCENE_LICENSE = "CC0-1.0";
