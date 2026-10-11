export type SceneProvenance =
  | "VERIFIED_SITE_GEOMETRY"
  | "CONFIGURED_SITE_GEOMETRY"
  | "SYNTHETIC_DEMO_GEOMETRY"
  | "UNAVAILABLE";

export type SiteZone = {
  id: string;
  label: string;
  center: [number, number];
  size: [number, number];
};

export type SiteSceneConfig = {
  schemaVersion: 1;
  id: string;
  title: string;
  provenance: SceneProvenance;
  units: "meters";
  boundary: { width: number; depth: number };
  building: {
    footprint: { width: number; depth: number };
    bays: { x: number; z: number };
    floors: number;
    floorHeight: number;
    phase: "foundation" | "frame" | "envelope";
  };
  components: { floors: boolean; columns: boolean; walls: boolean; scaffolding: boolean };
  siteFeatures: { perimeterFence: boolean; equipment: boolean; crane: boolean; roads: boolean };
  zones: SiteZone[];
};

export type SceneLayer = "structure" | "scaffolding" | "equipment" | "boundary" | "roads" | "zones" | "crane";
export type SceneEntity = {
  id: string;
  label: string;
  layer: SceneLayer;
  floor?: number;
  assetId?: string;
  primitive?: "box" | "cylinder" | "tube" | "zone";
  position: [number, number, number];
  scale: [number, number, number];
  rotation: [number, number, number];
  color?: string;
  opacity?: number;
  selectable: boolean;
};

export type AssembledScene = { config: SiteSceneConfig; entities: SceneEntity[] };
