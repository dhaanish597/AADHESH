"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as ThreeTypes from "three";
import type { SceneLayer, SceneProvenance, SiteSceneConfig } from "@/lib/site-scene/types";
import { assembleSiteScene } from "@/lib/site-scene/assemble";
import { SCENE_ASSETS } from "@/lib/site-scene/registry";
import { SITE_SCENE_FIXTURES } from "@/lib/site-scene/configs";
import { deterministicSiteSceneProvider, validateSceneProposal } from "@/lib/site-scene/provider";

type Props = { title: string; label: string; locale?: "en" | "hi"; landing?: boolean; activityIndex?: number };
type CameraActions = { rotate: () => void; pan: () => void; zoomIn: () => void; zoomOut: () => void; reset: () => void };
const LAYER_ORDER: SceneLayer[] = ["structure", "scaffolding", "equipment", "boundary", "roads", "zones", "crane"];
const LAYER_NAMES: Record<"en" | "hi", Record<SceneLayer, string>> = {
  en: { structure: "Structure", scaffolding: "Scaffolding", equipment: "Equipment", boundary: "Boundary", roads: "Road context", zones: "Named areas", crane: "Crane" },
  hi: { structure: "ढाँचा", scaffolding: "मचान", equipment: "उपकरण", boundary: "सीमा", roads: "सड़क संदर्भ", zones: "नामित क्षेत्र", crane: "क्रेन" },
};
const PROVENANCE_NAMES: Record<"en" | "hi", Record<SceneProvenance, string>> = {
  en: { VERIFIED_SITE_GEOMETRY: "VERIFIED SITE GEOMETRY", CONFIGURED_SITE_GEOMETRY: "CONFIGURED SITE GEOMETRY", SYNTHETIC_DEMO_GEOMETRY: "SYNTHETIC DEMO GEOMETRY", UNAVAILABLE: "SITE GEOMETRY UNAVAILABLE" },
  hi: { VERIFIED_SITE_GEOMETRY: "सत्यापित साइट ज्यामिति", CONFIGURED_SITE_GEOMETRY: "विन्यस्त साइट ज्यामिति", SYNTHETIC_DEMO_GEOMETRY: "सांकेतिक ज्यामिति", UNAVAILABLE: "साइट ज्यामिति उपलब्ध नहीं" },
};

export function SiteSceneExplorer({ title, label, locale = "en", landing = false, activityIndex = 0 }: Props) {
  const hi = locale === "hi";
  const [config, setConfig] = useState<SiteSceneConfig>(() => landing ? SITE_SCENE_FIXTURES[0] : SITE_SCENE_FIXTURES[1] ?? SITE_SCENE_FIXTURES[0]);
  const [configUpdating, setConfigUpdating] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const assembled = useMemo(() => assembleSiteScene(config), [config]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cityRequested, setCityRequested] = useState(false);
  const [cityState, setCityState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [floor, setFloor] = useState<number | "all">("all");
  const [visibleLayers, setVisibleLayers] = useState<Set<SceneLayer>>(() => new Set(LAYER_ORDER));
  const selected = assembled.entities.find((item) => item.id === selectedId) ?? null;
  const selectedZone = config.zones.find((zone) => `zone-${zone.id}` === selectedId);
  const layerText = LAYER_NAMES[locale];
  const selectedDescription = selectedZone
    ? (hi ? "यह एक सांकेतिक क्षेत्र है; इससे कोई अलग नियम या अनुमति तय नहीं होती।" : "This is a named illustrative area; it carries no separate rule or authorization.")
    : selected?.assetId
      ? `${SCENE_ASSETS[selected.assetId].purpose}. ${hi ? "कानूनी स्थिति के लिए कोई अलग नियम जुड़ा नहीं है।" : "No separate legal rule is attached to this object."}`
      : selected
        ? (hi ? "दृश्य का हिस्सा, कानूनी स्थिति से जुड़ा नहीं।" : "Visual scene component. No legal status is attached.")
        : (hi ? "किसी दृश्य वस्तु या क्षेत्र को चुनें।" : "Select a visible scene object or named area.");
  const toggleFullscreen = async () => {
    const viewport = viewportRef.current;
    if (!viewport?.requestFullscreen) {
      setConfigError(hi ? "इस ब्राउज़र में पूर्ण स्क्रीन उपलब्ध नहीं है।" : "Fullscreen is unavailable in this browser.");
      return;
    }
    try {
      if (document.fullscreenElement === viewport) await document.exitFullscreen();
      else await viewport.requestFullscreen();
    } catch {
      setConfigError(hi ? "पूर्ण स्क्रीन नहीं खुल सकी।" : "Fullscreen could not be opened.");
    }
  };

  return <section className="scene-explorer" data-selected={selected ? "true" : "false"} aria-label={hi ? "इंटरैक्टिव निर्माण स्थल दृश्य" : "Interactive construction site view"}>
    <div className="scene-explorer-heading"><div><span className="label">{label}</span><h2>{title}</h2></div><span className="scene-provenance">{PROVENANCE_NAMES[locale][config.provenance]}</span></div>
    <div className="scene-explorer-toolbar">
      <label className="scene-select-label">{hi ? "सांकेतिक लेआउट" : "Illustrative layout"}
        <select value={config.id} disabled={configUpdating} onChange={(event) => {
          setConfigUpdating(true); setConfigError(null); setSelectedId(null); setFloor("all");
          void deterministicSiteSceneProvider.propose({ configurationId: event.target.value }).then(validateSceneProposal).then((proposal) => { assembleSiteScene(proposal); setConfig(proposal); }).catch((error: unknown) => setConfigError(error instanceof Error ? error.message : "Scene layout could not be loaded.")).finally(() => setConfigUpdating(false));
        }} aria-label={hi ? "सांकेतिक साइट लेआउट चुनें" : "Choose an illustrative site layout"}>
          {SITE_SCENE_FIXTURES.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
        </select>
      </label>
      <label className="scene-select-label">{hi ? "मंज़िल" : "Floor"}
        <select value={floor} onChange={(event) => setFloor(event.target.value === "all" ? "all" : Number(event.target.value))} aria-label={hi ? "दिखाई जाने वाली मंज़िल चुनें" : "Choose a floor to emphasize"}>
          <option value="all">{hi ? "सभी मंज़िलें" : "All floors"}</option>
          {Array.from({ length: config.building.floors }, (_, i) => <option key={i + 1} value={i + 1}>{hi ? `मंज़िल ${i + 1}` : `Floor ${i + 1}`}</option>)}
        </select>
      </label>
    </div>
    {configUpdating ? <p className="scene-config-state" role="status">{hi ? "विन्यास तैयार हो रहा है…" : "Preparing the selected configuration…"}</p> : null}
    {configError ? <p className="scene-config-state is-error" role="alert">{configError}</p> : null}
    <ThreeScene assembled={assembled} floor={floor} visibleLayers={visibleLayers} selectedId={selectedId} onSelect={setSelectedId} viewportRef={viewportRef} landing={landing} activityIndex={activityIndex} cityRequested={cityRequested} onCityState={setCityState} />
    {landing ? <div className="scene-city-control">
      <div className="scene-city-copy"><span className="scene-city-status" aria-live="polite"><i className={cityState === "ready" ? "is-ready" : cityState === "error" ? "is-error" : ""}/>{cityState === "ready" ? "CITY MODEL READY" : cityState === "loading" ? "LOADING 3D CITY" : cityState === "error" ? "CITY MODEL UNAVAILABLE" : "CITY PACK 8 · 105 MESHES"}</span><small>On-demand · 13.3 MB · illustrative, not surveyed</small></div>
      <button type="button" onClick={() => setCityRequested((value) => !value)} aria-pressed={cityRequested} disabled={cityState === "loading"}>{cityRequested ? "Hide context" : "Load full city"}<span aria-hidden="true">{cityRequested ? "−" : "＋"}</span></button>
    </div> : null}
    <div className="scene-explorer-controls" role="group" aria-label={hi ? "कैमरा नियंत्रण" : "Camera controls"}>
      {(["rotate", "pan", "zoomIn", "zoomOut", "reset"] as const).map((action) => {
        const words = hi ? { rotate: "घुमाएँ", pan: "पैन", zoomIn: "ज़ूम +", zoomOut: "ज़ूम −", reset: "रीसेट" } : { rotate: "Rotate", pan: "Pan", zoomIn: "Zoom +", zoomOut: "Zoom −", reset: "Reset" };
        return <button key={action} type="button" onClick={() => window.dispatchEvent(new CustomEvent(`site-scene:${action}`))}>{words[action]}</button>;
      })}
      <button type="button" onClick={() => void toggleFullscreen()}>{hi ? "पूर्ण स्क्रीन" : "Fullscreen"}</button>
    </div>
    <div className="scene-explorer-layers" role="group" aria-label={hi ? "दृश्य परतें" : "Scene layers"}>
      {LAYER_ORDER.map((layer) => <label key={layer}><input type="checkbox" checked={visibleLayers.has(layer)} onChange={(event) => setVisibleLayers((current) => { const next = new Set(current); if (event.target.checked) next.add(layer); else next.delete(layer); return next; })} />{layerText[layer]}</label>)}
    </div>
    <div className="scene-selection" aria-live="polite"><div><span className="label">{hi ? "चयनित वस्तु" : "SELECTED OBJECT"}</span><strong>{selected?.label ?? (hi ? "कोई चयन नहीं" : "Nothing selected")}</strong><p>{selectedDescription}</p></div><span className="scene-selection-id">{selected?.id ?? (hi ? "सूची से चुनें" : "choose from list")}</span></div>
    <details className="scene-object-list"><summary>{hi ? "दृश्य में नामित वस्तुएँ और क्षेत्र" : `Named scene objects and areas (${assembled.entities.filter((item) => item.selectable).length})`}</summary>
      <div className="scene-object-list-content">{assembled.entities.filter((item) => item.selectable).map((item) => <button type="button" key={item.id} aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)}>{item.label}{item.floor ? <small>{hi ? `मंज़िल ${item.floor}` : `Floor ${item.floor}`}</small> : null}</button>)}</div>
    </details>
    <p className="scene-provenance-note">{hi ? "यह विन्यास उदाहरण के लिए बनाया गया है। इसे किसी वास्तविक साइट का सर्वेक्षण या नियम-आधारित प्रतिबंध न मानें।" : "This configurable illustration is not a survey of any real site. It does not determine legal restrictions."}</p>
  </section>;
}

function ThreeScene({ assembled, floor, visibleLayers, selectedId, onSelect, viewportRef, landing, activityIndex, cityRequested, onCityState }: { assembled: ReturnType<typeof assembleSiteScene>; floor: number | "all"; visibleLayers: Set<SceneLayer>; selectedId: string | null; onSelect: (id: string) => void; viewportRef: React.RefObject<HTMLDivElement | null>; landing: boolean; activityIndex: number; cityRequested: boolean; onCityState: (state: "idle" | "loading" | "ready" | "error") => void }) {
  const host = useRef<HTMLDivElement>(null);
  const cameraActions = useRef<CameraActions | null>(null);
  const selectedRef = useRef(selectedId);
  const floorRef = useRef(floor);
  const layersRef = useRef(visibleLayers);
  const selectRef = useRef(onSelect);
  const cityRequestedRef = useRef(cityRequested);
  const activityIndexRef = useRef(activityIndex);
  const cityStateCallbackRef = useRef(onCityState);
  const loadCityRef = useRef<(() => void) | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [readyConfig, setReadyConfig] = useState<string | null>(null);
  selectedRef.current = selectedId;
  floorRef.current = floor;
  layersRef.current = visibleLayers;
  selectRef.current = onSelect;
  cityRequestedRef.current = cityRequested;
  activityIndexRef.current = activityIndex;
  cityStateCallbackRef.current = onCityState;

  useEffect(() => {
    if (cityRequested) loadCityRef.current?.();
  }, [cityRequested]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let frame = 0;
    let cleanup: (() => void) | undefined;
    const liveListeners: [string, EventListener][] = [];
    const onCameraReady = (actions: CameraActions) => { cameraActions.current = actions; };
    const onControl = (name: keyof CameraActions) => cameraActions.current?.[name]();
    (Object.keys({ rotate: 1, pan: 1, zoomIn: 1, zoomOut: 1, reset: 1 }) as (keyof CameraActions)[]).forEach((name) => {
      const listener: EventListener = () => onControl(name);
      const eventName = `site-scene:${name}`;
      window.addEventListener(eventName, listener);
      liveListeners.push([eventName, listener]);
    });
    setFailure(null);
    setLoading(true);
    setReadyConfig(null);

    void (async () => {
      try {
        const THREE = await import("three");
        const [{ GLTFLoader }, { OrbitControls }] = await Promise.all([
          import("three/examples/jsm/loaders/GLTFLoader.js"),
          import("three/examples/jsm/controls/OrbitControls.js"),
        ]);
        const assetIds = [...new Set(assembled.entities.flatMap((entity) => entity.assetId ? [entity.assetId] : []))];
        const loader = new GLTFLoader();
        const gltfs = new Map(await Promise.all(assetIds.map(async (id) => [id, await loader.loadAsync(SCENE_ASSETS[id].path)] as const)));
        if (disposed || !element.clientWidth || !element.clientHeight) return;
        for (const [id, gltf] of gltfs) {
          const finish = SCENE_ASSETS[id].finish;
          if (!finish) continue;
          gltf.scene.traverse((object) => {
            if (!(object instanceof THREE.Mesh)) return;
            for (const material of (Array.isArray(object.material) ? object.material : [object.material])) {
              if (material instanceof THREE.MeshStandardMaterial) {
                material.color.set(finish);
                material.roughness = 0.88;
                material.metalness = 0.02;
                if (material.map) material.map.anisotropy = 4;
                material.needsUpdate = true;
              }
            }
          });
        }

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(landing ? "#14231d" : "#e5eff7");
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, landing ? 1.15 : 1.35));
        renderer.setSize(element.clientWidth, element.clientHeight);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
        renderer.shadowMap.enabled = !landing && window.innerWidth >= 760;
        renderer.shadowMap.type = THREE.PCFShadowMap;
        renderer.domElement.className = "scene-explorer-canvas";
        renderer.domElement.setAttribute("aria-hidden", "true");
        element.replaceChildren(renderer.domElement);
        const aspect = element.clientWidth / element.clientHeight;
        const camera = new THREE.PerspectiveCamera(38, aspect, 0.1, 200);
        const span = Math.max(assembled.config.boundary.width + 12, assembled.config.boundary.depth + 12);
        const target = new THREE.Vector3(0, assembled.config.building.floors * assembled.config.building.floorHeight * 0.36, 0);
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.target.copy(target);
        controls.enableDamping = true;
        controls.dampingFactor = 0.07;
        controls.minDistance = span * 0.42;
        controls.maxDistance = span * 2.5;
        controls.maxPolarAngle = Math.PI * 0.48;
        const reset = () => { camera.position.set(span * 0.84, span * 0.82, span * 0.92); controls.target.copy(target); controls.update(); };
        reset();
        scene.add(new THREE.HemisphereLight(landing ? 0xd9eee3 : 0xf5f9ff, landing ? 0x46584b : 0x75808a, 1.65));
        const sunlight = new THREE.DirectionalLight(0xffffff, 2.2);
        sunlight.position.set(span * 0.5, span, span * 0.35);
        sunlight.castShadow = renderer.shadowMap.enabled;
        sunlight.shadow.mapSize.set(1024, 1024);
        sunlight.shadow.camera.near = 0.5;
        sunlight.shadow.camera.far = span * 3;
        sunlight.shadow.bias = -0.00015;
        scene.add(sunlight);
        const grid = new THREE.GridHelper(Math.max(assembled.config.boundary.width + 8, assembled.config.boundary.depth + 8), 32, landing ? 0x55755f : 0x657c78, landing ? 0x405449 : 0x879c96);
        grid.position.y = 0.018;
        const gridMats = Array.isArray(grid.material) ? grid.material : [grid.material];
        gridMats.forEach((mat) => { mat.transparent = true; mat.opacity = 0.055; });
        scene.add(grid);

        const clickable: ThreeTypes.Object3D[] = [];
        const renderNodes = new Map<string, ThreeTypes.Object3D>();
        const generatedMaterials: InstanceType<typeof THREE.MeshStandardMaterial>[] = [];
        const makeMaterial = (color: string, opacity = 1) => {
          const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.86, transparent: opacity < 1, opacity, depthWrite: opacity >= 1, side: opacity < 1 ? THREE.DoubleSide : THREE.FrontSide });
          generatedMaterials.push(mat);
          return mat;
        };
        for (const entity of assembled.entities) {
          if (disposed) return;
          const root = new THREE.Group();
          root.name = entity.id;
          root.position.set(...entity.position);
          root.rotation.set(...entity.rotation);
          root.scale.set(...entity.scale);
          if (entity.assetId) {
            const object = gltfs.get(entity.assetId)?.scene.clone(true);
            if (!object) continue;
            root.add(object);
          } else if (entity.primitive === "box") {
            root.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), makeMaterial(entity.color ?? "#879287", entity.opacity)));
          } else if (entity.primitive === "tube") {
            root.add(new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 1, 7), makeMaterial(entity.color ?? "#909893")));
          } else if (entity.primitive === "zone") {
            const face = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), makeMaterial(entity.color ?? "#4e9e7a", entity.opacity ?? 0.3));
            face.rotation.x = -Math.PI / 2;
            face.scale.set(0.98, 0.98, 1);
            root.rotation.set(0, 0, 0);
            root.scale.set(entity.scale[0], 1, entity.scale[2]);
            root.add(face);
          }
          root.userData.sceneObjectId = entity.id;
          root.traverse((child) => {
            if (!(child instanceof THREE.Mesh)) return;
            child.castShadow = true;
            child.receiveShadow = true;
            if (entity.selectable) clickable.push(child);
          });
          scene.add(root);
          renderNodes.set(entity.id, root);
          root.visible = layersRef.current.has(entity.layer) && (floorRef.current === "all" || entity.floor === undefined || entity.floor === floorRef.current);
        }
        let cityRoot: InstanceType<typeof THREE.Group> | null = null;
        let cityPromise: Promise<void> | null = null;
        const loadCity = () => {
          if (!landing || cityRoot || cityPromise) return;
          cityStateCallbackRef.current("loading");
          cityPromise = loader.loadAsync("/models/city-pack-8.glb").then((gltf) => {
            if (disposed) {
              gltf.scene.traverse((item) => {
                if (item instanceof THREE.Mesh) {
                  item.geometry.dispose();
                  for (const material of (Array.isArray(item.material) ? item.material : [item.material])) {
                    for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose();
                    material.dispose();
                  }
                }
              });
              return;
            }
            const model = gltf.scene;
            model.updateMatrixWorld(true);
            const bounds = new THREE.Box3().setFromObject(model);
            const center = bounds.getCenter(new THREE.Vector3());
            const size = bounds.getSize(new THREE.Vector3());
            const scale = 36 / Math.max(size.x, size.z, 1);
            cityRoot = new THREE.Group();
            cityRoot.name = "City Pack 8 · background context";
            cityRoot.scale.setScalar(scale);
            cityRoot.position.set(-center.x * scale, 0.08 - bounds.min.y * scale, -center.z * scale - 29);
            model.traverse((item) => {
              if (!(item instanceof THREE.Mesh)) return;
              item.castShadow = false;
              item.receiveShadow = false;
              item.frustumCulled = true;
            });
            cityRoot.add(model);
            scene.add(cityRoot);
            cityStateCallbackRef.current("ready");
          }).catch(() => { cityPromise = null; cityStateCallbackRef.current("error"); });
        };
        loadCityRef.current = loadCity;
        if (cityRequestedRef.current) loadCity();
        let selectionBox: InstanceType<typeof THREE.BoxHelper> | null = null;
        let hoverBox: InstanceType<typeof THREE.BoxHelper> | null = null;
        let hoveredId: string | null = null;
        const clearBox = (box: InstanceType<typeof THREE.BoxHelper> | null) => {
          if (box) { scene.remove(box); box.geometry.dispose(); (box.material as InstanceType<typeof THREE.LineBasicMaterial>).dispose(); }
        };
        const showSelection = (id: string | null) => {
          clearBox(selectionBox);
          selectionBox = null;
          const object = id ? renderNodes.get(id) : null;
          if (object?.visible) {
            object.updateWorldMatrix(true, true);
            selectionBox = new THREE.BoxHelper(object, 0x1769e8);
            selectionBox.material.depthTest = false;
            selectionBox.renderOrder = 10;
            scene.add(selectionBox);
          }
        };
        const showHover = (id: string | null) => {
          const nextId = id !== selectedRef.current && renderNodes.get(id ?? "")?.visible ? id : null;
          if (nextId === hoveredId) return;
          hoveredId = nextId;
          clearBox(hoverBox);
          hoverBox = null;
          const object = hoveredId ? renderNodes.get(hoveredId) : null;
          if (object?.visible) {
            object.updateWorldMatrix(true, true);
            hoverBox = new THREE.BoxHelper(object, 0x7598c7);
            hoverBox.material.depthTest = false;
            hoverBox.renderOrder = 9;
            scene.add(hoverBox);
          }
        };
        let lastSelection = selectedRef.current;
        let lastActivity = -1;
        showSelection(lastSelection);
        const raycaster = new THREE.Raycaster();
        const pointer = new THREE.Vector2();
        let down: [number, number] | null = null;
        const setRay = (event: PointerEvent) => {
          const rect = renderer.domElement.getBoundingClientRect();
          pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
          raycaster.setFromCamera(pointer, camera);
          return raycaster.intersectObjects(clickable.filter((mesh) => { let node: ThreeTypes.Object3D | null = mesh; while (node) { if (!node.visible) return false; node = node.parent; } return true; }), false)[0]?.object ?? null;
        };
        const pointerDown = (event: PointerEvent) => { down = [event.clientX, event.clientY]; };
        const pointerUp = (event: PointerEvent) => {
          if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 7) { down = null; return; }
          const hit = setRay(event);
          let root: ThreeTypes.Object3D | null = hit;
          while (root && !root.userData.sceneObjectId) root = root.parent;
          const id = root?.userData.sceneObjectId as string | undefined;
          if (id) selectRef.current(id);
          down = null;
        };
        const pointerMove = (event: PointerEvent) => {
          if (down) return;
          const hit = setRay(event);
          renderer.domElement.style.cursor = hit ? "pointer" : "grab";
          let root: ThreeTypes.Object3D | null = hit;
          while (root && !root.userData.sceneObjectId) root = root.parent;
          showHover(root?.userData.sceneObjectId as string | null ?? null);
        };
        const pointerLeave = () => { down = null; renderer.domElement.style.cursor = "grab"; showHover(null); };
        renderer.domElement.addEventListener("pointerdown", pointerDown);
        renderer.domElement.addEventListener("pointerup", pointerUp);
        renderer.domElement.addEventListener("pointermove", pointerMove);
        renderer.domElement.addEventListener("pointerleave", pointerLeave);
        const resize = new ResizeObserver(() => {
          if (!element.clientWidth || !element.clientHeight) return;
          camera.aspect = element.clientWidth / element.clientHeight;
          camera.updateProjectionMatrix();
          renderer.setSize(element.clientWidth, element.clientHeight);
        });
        resize.observe(element);
        const actions: CameraActions = {
          rotate: () => { controls.rotateLeft(Math.PI / 6); controls.update(); },
          pan: () => { controls.pan(48, 0); controls.update(); },
          zoomIn: () => { controls.dollyIn(1.25); controls.update(); },
          zoomOut: () => { controls.dollyOut(1.25); controls.update(); },
          reset,
        };
        onCameraReady(actions);
        let inView = true;
        const render = () => {
          if (disposed || !inView || document.hidden) { frame = 0; return; }
          for (const entity of assembled.entities) {
            const node = renderNodes.get(entity.id);
            if (node) node.visible = layersRef.current.has(entity.layer) && (floorRef.current === "all" || entity.floor === undefined || entity.floor === floorRef.current);
          }
          if (landing && lastActivity !== activityIndexRef.current) {
            const activeZone = ["zone-work-area", "zone-work-area", "zone-material-storage", "zone-material-storage"][activityIndexRef.current] ?? "zone-work-area";
            for (const [id, node] of renderNodes) {
              if (!id.startsWith("zone-")) continue;
              node.traverse((part) => {
                if (!(part instanceof THREE.Mesh)) return;
                const materials = Array.isArray(part.material) ? part.material : [part.material];
                materials.forEach((material) => {
                  if (!(material instanceof THREE.MeshStandardMaterial)) return;
                  material.color.set(id === activeZone ? "#20d3a1" : "#42675b");
                  material.opacity = id === activeZone ? 0.52 : 0.17;
                });
              });
            }
            lastActivity = activityIndexRef.current;
          }
          if (cityRoot) cityRoot.visible = cityRequestedRef.current;
          if (lastSelection !== selectedRef.current || (lastSelection !== null && !renderNodes.get(lastSelection)?.visible && selectionBox !== null) || (lastSelection !== null && renderNodes.get(lastSelection)?.visible && selectionBox === null)) { lastSelection = selectedRef.current; showSelection(lastSelection); }
          controls.update();
          renderer.render(scene, camera);
          frame = window.requestAnimationFrame(render);
        };
        const visibility = new IntersectionObserver(([entry]) => {
          inView = entry.isIntersecting;
          if (inView && !document.hidden && !frame) frame = window.requestAnimationFrame(render);
          else if (!inView && frame) { window.cancelAnimationFrame(frame); frame = 0; }
        }, { rootMargin: "120px" });
        visibility.observe(element);
        const onVisibilityChange = () => {
          if (document.hidden && frame) { window.cancelAnimationFrame(frame); frame = 0; }
          else if (!document.hidden && inView && !frame) frame = window.requestAnimationFrame(render);
        };
        document.addEventListener("visibilitychange", onVisibilityChange);
        frame = window.requestAnimationFrame(render);
        setLoading(false);
        setReadyConfig(assembled.config.id);
        cleanup = () => {
          window.cancelAnimationFrame(frame);
          visibility.disconnect();
          document.removeEventListener("visibilitychange", onVisibilityChange);
          loadCityRef.current = null;
          resize.disconnect();
          renderer.domElement.removeEventListener("pointerdown", pointerDown);
          renderer.domElement.removeEventListener("pointerup", pointerUp);
          renderer.domElement.removeEventListener("pointermove", pointerMove);
          renderer.domElement.removeEventListener("pointerleave", pointerLeave);
          controls.dispose();
          renderer.dispose();
          clearBox(selectionBox);
          clearBox(hoverBox);
          const geometries = new Set<ThreeTypes.BufferGeometry>();
          const materials = new Set<ThreeTypes.Material>();
          const textures = new Set<ThreeTypes.Texture>();
          scene.traverse((node) => {
            if (node instanceof THREE.Mesh || node instanceof THREE.LineSegments) {
              geometries.add(node.geometry);
              for (const mat of (Array.isArray(node.material) ? node.material : [node.material])) {
                materials.add(mat);
                for (const value of Object.values(mat)) if (value instanceof THREE.Texture) textures.add(value);
              }
            }
          });
          geometries.forEach((geometry) => geometry.dispose());
          materials.forEach((mat) => mat.dispose());
          textures.forEach((texture) => texture.dispose());
          cityStateCallbackRef.current("idle");
          generatedMaterials.forEach((mat) => mat.dispose());
          cameraActions.current = null;
        };
      } catch (error) {
        if (!disposed) { setFailure(error instanceof Error ? error.message : "The 3D site view could not be loaded."); setLoading(false); setReadyConfig(assembled.config.id); }
      }
    })();
    return () => { disposed = true; cleanup?.(); cameraActions.current = null; liveListeners.forEach(([name, listener]) => window.removeEventListener(name, listener)); };
  }, [assembled, landing]);

  return <div ref={viewportRef} className="scene-explorer-viewport" role="group" aria-label="Three-dimensional site model" data-state={readyConfig === assembled.config.id ? "ready" : "loading"}>
    <div className="scene-canvas-host" ref={host} />
    {loading && !failure ? <div className="scene-render-loading" role="status">Loading 3D scene…</div> : null}
    {failure ? <div className="scene-render-error" role="status"><strong>{"3D view unavailable"}</strong><span>{failure}</span><span>Scene selection remains available from the accessible object list.</span></div> : null}
    {!failure ? <div className="scene-canvas-hint">{"Drag to rotate · two-finger pan · scroll to zoom"}</div> : null}
  </div>;
}
