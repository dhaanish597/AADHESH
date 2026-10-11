"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Mesh as ThreeMesh, MeshStandardMaterial, WebGLRenderer } from "three";
import type { SceneObjectKey } from "@/components/OperationsWorkspace";
import type { SupervisorPayload } from "@/lib/types";

type Zone = { key: SceneObjectKey; label: string; status: "active" | "warn" | "unknown" | "idle"; indicator: string; description: string; position: [number, number, number] };

function zonesFor(payload: SupervisorPayload): Zone[] {
  const findObligation = (matches: (item: SupervisorPayload["obligations"][number]) => boolean) =>
    payload.obligations.find((item) => item.applicable === true && matches(item))
    ?? payload.obligations.find((item) => item.applicable === null && matches(item))
    ?? null;
  const dust = findObligation((item) => /dust/i.test(item.label));
  const restriction = findObligation((item) => /restrict/i.test(`${item.obligation_id} ${item.label} ${item.required_action} ${item.reason}`));
  const status = (item: typeof dust): Zone["status"] => !item || item.applicable === false || item.status === "NOT_APPLICABLE" ? "idle" : item.status === "MET" ? "active" : item.status === "NOT_MET" ? "warn" : "unknown";
  const waiting = Math.max(0, payload.impact.documented - payload.impact.acknowledged);
  return [
    { key: "activity-zone", label: "Work zone", status: payload.site.activity_type ? "active" : "unknown", indicator: payload.site.activity_type ? "Profile on file" : "Unknown", description: `Site activity on record: ${payload.site.activity_type ?? "not recorded"}.`, position: [-2.1, .18, .1] },
    { key: "dust-zone", label: "Dust controls", status: status(dust), indicator: dust?.status ?? "No linked record", description: dust ? `Resolver obligation: ${dust.status}${dust.applicable === false ? " (not applicable)" : ""}.` : "No dust obligation was returned by the resolver.", position: [1.55, .18, -1.05] },
    { key: "restricted-area", label: "Work restriction", status: status(restriction), indicator: restriction?.status ?? "No linked record", description: restriction ? `Resolver obligation: ${restriction.status}${restriction.applicable === false ? " (not applicable)" : ""}.` : "No restriction obligation was returned by the resolver.", position: [1.7, .18, 1.15] },
    { key: "worker-point", label: "Worker point", status: waiting ? "warn" : "active", indicator: `${waiting} awaiting`, description: `${waiting} issued Parchis await acknowledgement by their workers.`, position: [-2.05, .18, 1.1] },
    { key: "evidence-station", label: "Evidence desk", status: payload.fully_sourced ? "active" : "warn", indicator: payload.fully_sourced ? "Sources verified" : "Review needed", description: payload.fully_sourced ? "Returned obligations have verified source links." : "At least one returned obligation needs source review.", position: [0, .18, 2.05] },
    { key: "terminal", label: "Site terminal", status: payload.resolved_at ? "active" : "unknown", indicator: payload.resolved_at ? "Resolved" : "Unknown", description: `Resolver state updated ${new Date(payload.resolved_at).toLocaleString()}.`, position: [-2.2, .18, -1.25] },
  ];
}

function SiteFallback({ zones, selectedObject, onSelectObject, reason }: { zones: Zone[]; selectedObject: SceneObjectKey | null; onSelectObject: (key: SceneObjectKey) => void; reason: string }) {
  return <div className="site-scene-fallback" role="group" aria-label="Construction site overview">
    <div className="site-fallback-building" aria-hidden="true"><span /><span /><span /></div>
    <p className="site-fallback-note">3D view unavailable · schematic view</p>
    <div className="site-fallback-zones">{zones.map((zone) => <button key={zone.key} type="button" aria-label={`${zone.label}. ${zone.indicator}. ${zone.description}`} aria-pressed={selectedObject === zone.key} onClick={() => onSelectObject(zone.key)}>
      <span className={`scene-status scene-status-${zone.status}`} aria-hidden="true" />{zone.label}<small>{zone.description}</small><em>{zone.indicator}</em>
    </button>)}</div>
    <p className="sr-only">{reason}</p>
  </div>;
}

export function SiteScene3D({ payload, selectedObject, onSelectObject }: { payload: SupervisorPayload; selectedObject: SceneObjectKey | null; onSelectObject: (key: SceneObjectKey) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const zones = useMemo(() => zonesFor(payload), [payload]);
  const selectedRef = useRef(selectedObject);
  const onSelectRef = useRef(onSelectObject);
  const resetCameraRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    selectedRef.current = selectedObject;
    onSelectRef.current = onSelectObject;
  }, [selectedObject, onSelectObject]);

  useEffect(() => {
    let disposed = false;
    let frame = 0;
    let activeRenderer: WebGLRenderer | null = null;
    let cleanup: (() => void) | undefined;
    const element = host.current;
    if (!element) return;
    setFallbackReason(null);
    setLoading(true);

    void (async () => {
      try {
        const THREE = await import("three");
        const [{ GLTFLoader }, { OrbitControls }] = await Promise.all([
          import("three/examples/jsm/loaders/GLTFLoader.js"),
          import("three/examples/jsm/controls/OrbitControls.js"),
        ]);
        if (disposed) return;
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
        activeRenderer = renderer;
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.35));
        renderer.setSize(element.clientWidth, element.clientHeight);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
        renderer.shadowMap.enabled = window.innerWidth >= 760;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.domElement.setAttribute("aria-hidden", "true");
        renderer.domElement.className = "site-scene-canvas";
        element.replaceChildren(renderer.domElement);

        const scene = new THREE.Scene();
        scene.background = new THREE.Color("#e5eff7");
        const camera = new THREE.PerspectiveCamera(36, element.clientWidth / Math.max(1, element.clientHeight), .1, 100);
        camera.position.set(7, 7, 9);
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.target.set(0, .6, 0);
        controls.enableDamping = true;
        controls.dampingFactor = .08;
        controls.minDistance = 6;
        controls.maxDistance = 15;
        controls.maxPolarAngle = Math.PI * .47;
        resetCameraRef.current = () => {
          camera.position.set(7, 7, 9);
          controls.target.set(0, .6, 0);
          controls.update();
        };
        scene.add(new THREE.HemisphereLight(0xf5f9ff, 0x75808a, 1.7));
        const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
        keyLight.position.set(5, 9, 4);
        keyLight.castShadow = renderer.shadowMap.enabled;
        keyLight.shadow.mapSize.set(1024, 1024);
        keyLight.shadow.bias = -0.00015;
        scene.add(keyLight);

        const material = (color: string, roughness = .86) => new THREE.MeshStandardMaterial({ color, roughness, metalness: .04 });
        const ground = new THREE.Mesh(new THREE.BoxGeometry(7.6, .24, 5.6), material("#c5d0d2"));
        ground.position.y = -.12;
        ground.receiveShadow = true;
        scene.add(ground);
        const slab = new THREE.Mesh(new THREE.BoxGeometry(5.8, .08, 3.7), material("#d3d9db"));
        slab.position.set(.25, .04, 0);
        slab.receiveShadow = true;
        scene.add(slab);
        const grid = new THREE.GridHelper(7.4, 18, 0x8f9a8f, 0x647066);
        grid.position.y = .012;
        const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
        gridMaterials.forEach((item) => { item.transparent = true; item.opacity = .06; });
        scene.add(grid);

        const group = new THREE.Group();
        group.position.set(.1, .1, -.15);
        scene.add(group);
        const loader = new GLTFLoader();
        const modelUrls = ["/models/kenney/building-a.glb", "/models/kenney/building-c.glb", "/models/kenney/column.glb", "/models/kenney/construction-fence.glb"];
        const models = await Promise.all(modelUrls.map((url) => loader.loadAsync(url)));
        if (disposed) { renderer.dispose(); return; }
        const buildingA = models[0].scene;
        buildingA.scale.setScalar(3.6);
        buildingA.position.set(-.45, .1, -.1);
        group.add(buildingA);
        const buildingC = models[1].scene;
        buildingC.scale.set(2.2, 2.6, 2.2);
        buildingC.position.set(1.35, .1, -.25);
        group.add(buildingC);
        for (const [x, z] of [[-1.35, -.9], [-.45, -.9], [.45, -.9], [1.35, -.9]] as const) {
          const fence = models[3].scene.clone();
          fence.position.set(x, .12, z);
          fence.scale.set(2, 1.2, 1.2);
          group.add(fence);
        }
        for (const [x, z] of [[-.7, .9], [.65, .9]] as const) {
          const column = models[2].scene.clone();
          column.scale.setScalar(.48);
          column.position.set(x, .08, z);
          group.add(column);
        }
        group.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          object.castShadow = true;
          object.receiveShadow = true;
        });

        const statusColor = (status: Zone["status"]) => status === "warn" ? 0xd88a11 : status === "active" ? 0x21834d : status === "unknown" ? 0x1769e8 : 0x7f8c9b;
        const markers = new Map<SceneObjectKey, ThreeMesh>();
        for (const zone of zones) {
          const marker = new THREE.Mesh(new THREE.CylinderGeometry(.29, .36, .075, 24), new THREE.MeshStandardMaterial({ color: statusColor(zone.status), emissive: statusColor(zone.status), emissiveIntensity: .22, roughness: .6 }));
          marker.position.set(...zone.position);
          marker.userData.zoneKey = zone.key;
          marker.userData.baseColor = statusColor(zone.status);
          scene.add(marker);
          markers.set(zone.key, marker);
          const post = new THREE.Mesh(new THREE.CylinderGeometry(.028, .028, .34, 8), material("#d9dfd6"));
          post.position.set(zone.position[0], zone.position[1] + .2, zone.position[2]);
          scene.add(post);
        }
        const applySelection = () => markers.forEach((marker, key) => {
          const active = selectedRef.current === key;
          const meshMaterial = marker.material as MeshStandardMaterial;
          meshMaterial.color.set(active ? 0x1769e8 : marker.userData.baseColor as number);
          meshMaterial.emissiveIntensity = active ? .4 : .12;
          marker.scale.setScalar(active ? 1.18 : 1);
        });
        applySelection();
        const raycaster = new THREE.Raycaster();
        const pointer = new THREE.Vector2();
        const onClick = (event: MouseEvent) => {
          const rect = renderer.domElement.getBoundingClientRect();
          pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
          raycaster.setFromCamera(pointer, camera);
          const hit = raycaster.intersectObjects([...markers.values()])[0]?.object;
          if (hit?.userData.zoneKey) onSelectRef.current(hit.userData.zoneKey as SceneObjectKey);
        };
        renderer.domElement.addEventListener("click", onClick);
        const resize = new ResizeObserver(() => {
          if (!element.clientWidth || !element.clientHeight) return;
          camera.aspect = element.clientWidth / element.clientHeight;
          camera.updateProjectionMatrix();
          renderer.setSize(element.clientWidth, element.clientHeight);
        });
        resize.observe(element);
        const render = () => {
          if (disposed) return;
          applySelection();
          controls.update();
          renderer.render(scene, camera);
          frame = window.requestAnimationFrame(render);
        };
        render();
        setLoading(false);
        cleanup = () => {
          window.cancelAnimationFrame(frame);
          resize.disconnect();
          renderer.domElement.removeEventListener("click", onClick);
          controls.dispose();
          renderer.dispose();
          scene.traverse((object) => {
            if (object instanceof THREE.Mesh) {
              object.geometry.dispose();
              const materials = Array.isArray(object.material) ? object.material : [object.material];
              materials.forEach((item) => item.dispose());
            }
          });
        };
      } catch (error) {
        activeRenderer?.dispose();
        if (!disposed) {
          setFallbackReason(error instanceof Error ? error.message : "3D rendering could not be initialized.");
          setLoading(false);
        }
      }
    })();

    return () => { disposed = true; cleanup?.(); resetCameraRef.current = null; };
  }, [payload, zones]);

  return <div className="site-scene" role="group" aria-label="Interactive construction site model">
    <div className="scene-topline"><span className="label">Site model · schematic</span><span>Drag to orbit · scroll to zoom</span></div>
    {fallbackReason ? <SiteFallback zones={zones} selectedObject={selectedObject} onSelectObject={onSelectObject} reason={fallbackReason} /> : <>
      <div className="site-scene-surface site-scene-3d" aria-label="Three-dimensional construction site model">
        <div className="site-scene-canvas-host" ref={host} />
        {loading && <div className="scene-loading" role="status">Loading site model…</div>}
      </div>
      <button type="button" className="scene-reset" onClick={() => resetCameraRef.current?.()}>Reset view</button>
      <div className="scene-zone-list" role="group" aria-label="Site zones">
        {zones.map((zone) => <button key={zone.key} type="button" aria-label={`${zone.label}. ${zone.indicator}. ${zone.description}`} aria-pressed={selectedObject === zone.key} onClick={() => onSelectObject(zone.key)}>
          <span className={`scene-status scene-status-${zone.status}`} aria-hidden="true" />{zone.label}<span className="scene-zone-state">{zone.indicator}</span>
        </button>)}
      </div>
    </>}
    <p className="site-scene-note">Schematic zones link to the site level resolver record; they are not independent compliance determinations or live readings.</p>
  </div>;
}
