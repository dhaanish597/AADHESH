'use client';

import React, { useRef, useEffect } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { SiteElement, CameraPreset } from './types';
import { Building } from './Building';
import { WorkZones } from './WorkZones';
import { Crane } from './Crane';
import { SiteVehicles } from './SiteVehicles';

interface SceneProps {
  onSelect: (element: SiteElement | null) => void;
  selectedId: string | null;
  explodedView: boolean;
  cameraPreset: CameraPreset;
  elementsMap: Map<string, SiteElement>;
  isCraneAnimated?: boolean;
  onHover?: (element: SiteElement | null) => void;
}

// Preset coordinates
const PRESET_COORDINATES: Record<
  CameraPreset,
  { pos: [number, number, number]; target: [number, number, number] }
> = {
  overview: { pos: [48, 38, 48], target: [0, 6, 0] },
  building: { pos: [26, 22, 26], target: [0, 10, 0] },
  crane: { pos: [-36, 32, -8], target: [-18, 24, -16] },
  ground: { pos: [0, 14, 52], target: [0, 2, 10] },
  'focus-selected': { pos: [28, 24, 28], target: [0, 8, 0] },
};

function getFocusTarget(
  selectedId: string | null,
  elementsMap: Map<string, SiteElement>,
): { pos: [number, number, number]; target: [number, number, number] } | null {
  if (!selectedId) return null;

  // Floors
  if (selectedId.startsWith('floor-')) {
    const floorIdx = parseInt(selectedId.replace('floor-', ''), 10) || 0;
    const y = floorIdx * 4.2;
    return {
      pos: [22, y + 14, 22],
      target: [0, y + 2, 0],
    };
  }

  // Crane
  if (selectedId === 'crane-tower-1') {
    return {
      pos: [-36, 34, -4],
      target: [-18, 24, -16],
    };
  }

  // Zones & Vehicles
  const elem = elementsMap.get(selectedId);
  if (elem?.coordinates) {
    const [cx, cy, cz] = elem.coordinates;
    return {
      pos: [cx + 16, cy + 14, cz + 16],
      target: [cx, cy, cz],
    };
  }

  // Work zones
  const zoneTargets: Record<
    string,
    { pos: [number, number, number]; target: [number, number, number] }
  > = {
    'zone-piling': { pos: [38, 16, -2], target: [24, 2, -14] },
    'activity-zone': { pos: [38, 16, -2], target: [24, 2, -14] },
    'zone-demolition': { pos: [-38, 16, 16], target: [-24, 2, 2] },
    'restricted-area': { pos: [-38, 16, 16], target: [-24, 2, 2] },
    'zone-material': { pos: [-36, 16, -6], target: [-22, 2, -20] },
    'zone-dust': { pos: [36, 16, 32], target: [22, 2, 18] },
    'dust-zone': { pos: [36, 16, 32], target: [22, 2, 18] },
    'zone-access': { pos: [18, 14, 44], target: [0, 2, 30] },
    'zone-worker': { pos: [42, 16, -14], target: [28, 2, -28] },
    'worker-point': { pos: [42, 16, -14], target: [28, 2, -28] },
    'zone-evidence': { pos: [-44, 16, 36], target: [-30, 2, 22] },
    'evidence-station': { pos: [-44, 16, 36], target: [-30, 2, 22] },
    'vehicle-tipper-1': { pos: [22, 12, 38], target: [6, 2, 28] },
    'vehicle-excavator-1': { pos: [-36, 14, 8], target: [-23, 2, -4] },
    'vehicle-sprinkler-1': { pos: [34, 14, 22], target: [20, 2, 8] },
    'building-main': { pos: [28, 24, 28], target: [0, 10, 0] },
    terminal: { pos: [28, 24, 28], target: [0, 10, 0] },
  };

  return zoneTargets[selectedId] ?? null;
}

function CameraController({
  preset,
  selectedId,
  elementsMap,
}: {
  preset: CameraPreset;
  selectedId: string | null;
  elementsMap: Map<string, SiteElement>;
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const targetVec = useRef(
    new THREE.Vector3(...PRESET_COORDINATES.overview.target),
  );
  const posVec = useRef(new THREE.Vector3(...PRESET_COORDINATES.overview.pos));
  const isTransitioning = useRef(true);

  // Transition trigger on preset change or focus-selected
  useEffect(() => {
    if (preset === 'focus-selected' && selectedId) {
      const focus = getFocusTarget(selectedId, elementsMap);
      if (focus) {
        posVec.current.set(...focus.pos);
        targetVec.current.set(...focus.target);
        isTransitioning.current = true;
        return;
      }
    }

    const config = PRESET_COORDINATES[preset];
    if (config) {
      posVec.current.set(...config.pos);
      targetVec.current.set(...config.target);
      isTransitioning.current = true;
    }
  }, [preset, selectedId, elementsMap]);

  useFrame((_, delta) => {
    if (!controlsRef.current) return;
    if (isTransitioning.current) {
      const lerpSpeed = Math.min(delta * 4.5, 0.18);
      camera.position.lerp(posVec.current, lerpSpeed);
      controlsRef.current.target.lerp(targetVec.current, lerpSpeed);
      controlsRef.current.update();

      if (
        camera.position.distanceTo(posVec.current) < 0.1 &&
        controlsRef.current.target.distanceTo(targetVec.current) < 0.1
      ) {
        isTransitioning.current = false;
      }
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      target={[0, 6, 0]}
      minPolarAngle={Math.PI / 12}
      maxPolarAngle={Math.PI / 2.15} // Prevents camera from dipping under ground plane
      minDistance={12}
      maxDistance={125}
      enableDamping
      dampingFactor={0.07}
      rotateSpeed={0.8}
      zoomSpeed={0.9}
      panSpeed={0.8}
    />
  );
}

export function Scene({
  onSelect,
  selectedId,
  explodedView,
  cameraPreset,
  elementsMap,
  isCraneAnimated = false,
  onHover,
}: SceneProps) {
  return (
    <>
      {/* Background color — sleek charcoal control room tone */}
      <color attach="background" args={['#101512']} />

      {/* Lighting Architecture: Hemisphere, Sun, Fill, Bounce */}
      <hemisphereLight args={['#e0f2fe', '#1e2922', 1.05]} />
      <ambientLight intensity={0.7} color="#f0fdf4" />
      <directionalLight
        castShadow
        position={[45, 68, -25]}
        intensity={2.2}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-55}
        shadow-camera-right={55}
        shadow-camera-top={55}
        shadow-camera-bottom={-55}
        shadow-bias={-0.0001}
      />
      <directionalLight
        position={[-45, 30, 45]}
        intensity={0.95}
        color="#a7f3d0"
      />

      {/* Site Ground Group */}
      <group position={[0, -0.2, 0]}>
        {/* Main Earth / Compacted Soil Ground Plane */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0, 0]}
          receiveShadow
          onClick={() => onSelect(null)}
        >
          <planeGeometry args={[140, 140]} />
          <meshStandardMaterial
            color="#171e19"
            roughness={0.92}
            metalness={0.04}
          />
        </mesh>

        {/* Access Road Paving Strip */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0.02, 28]}
          receiveShadow
          onClick={() => onSelect(null)}
        >
          <planeGeometry args={[130, 16]} />
          <meshStandardMaterial color="#212a23" roughness={0.8} />
        </mesh>

        {/* Central Building Foundation Base Mat */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0.04, 0]}
          receiveShadow
        >
          <planeGeometry args={[36, 26]} />
          <meshStandardMaterial color="#28342b" roughness={0.85} />
        </mesh>

        {/* Site Boundary Wall Wireframe */}
        <lineSegments position={[0, 1.2, 0]}>
          <edgesGeometry args={[new THREE.BoxGeometry(100, 2.4, 100)]} />
          <lineBasicMaterial color="#3b4d40" linewidth={1} />
        </lineSegments>

        {/* Precision Analytical Ground Grid */}
        <Grid
          position={[0, 0.06, 0]}
          args={[140, 140]}
          cellSize={4}
          cellThickness={0.9}
          cellColor="#26352b"
          sectionSize={20}
          sectionThickness={1.5}
          sectionColor="#3d5244"
          fadeDistance={80}
        />

        {/* 3D Elements with dynamic elementsMap data */}
        <Building
          onSelect={onSelect}
          selectedId={selectedId}
          explodedView={explodedView}
          elementsMap={elementsMap}
          onHover={onHover}
        />
        <WorkZones
          onSelect={onSelect}
          selectedId={selectedId}
          elementsMap={elementsMap}
          onHover={onHover}
        />
        <Crane
          onSelect={onSelect}
          selectedId={selectedId}
          elementsMap={elementsMap}
          isAnimated={isCraneAnimated}
          onHover={onHover}
        />
        <SiteVehicles
          onSelect={onSelect}
          selectedId={selectedId}
          elementsMap={elementsMap}
          onHover={onHover}
        />
      </group>

      <CameraController
        preset={cameraPreset}
        selectedId={selectedId}
        elementsMap={elementsMap}
      />
    </>
  );
}

