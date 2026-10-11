'use client';

import React, { useMemo, useState, useRef } from 'react';
import * as THREE from 'three';
import { ThreeEvent, useFrame } from '@react-three/fiber';
import { SiteElement } from './types';

interface CraneProps {
  onSelect: (element: SiteElement) => void;
  selectedId: string | null;
  elementsMap: Map<string, SiteElement>;
  isAnimated?: boolean;
  onHover?: (element: SiteElement | null) => void;
}

export function Crane({
  onSelect,
  selectedId,
  elementsMap,
  isAnimated = false,
  onHover,
}: CraneProps) {
  const [hovered, setHovered] = useState(false);
  const isSelected = selectedId === 'crane-tower-1';
  const craneElem = elementsMap.get('crane-tower-1');
  const presentationState = craneElem?.presentationState ?? 'verified';

  const slewingRef = useRef<THREE.Group>(null);
  const trolleyRef = useRef<THREE.Group>(null);

  // Optional subtle illustrative motion (clearly labeled in UI)
  useFrame((state) => {
    if (!slewingRef.current) return;
    if (isAnimated) {
      const t = state.clock.getElapsedTime();
      // Slow gentle slewing back and forth (+/- 14 degrees)
      slewingRef.current.rotation.y = Math.sin(t * 0.35) * 0.25;
      if (trolleyRef.current) {
        // Trolley travels between 9m and 16m along jib
        trolleyRef.current.position.x = 12 + Math.sin(t * 0.25) * 3;
      }
    } else {
      slewingRef.current.rotation.y = 0;
      if (trolleyRef.current) {
        trolleyRef.current.position.x = 12;
      }
    }
  });

  const handleSelect = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    if (craneElem) {
      onSelect(craneElem);
    }
  };

  // Dynamic colors
  let craneColor = '#f5b041'; // industrial safety amber
  let emissiveColor = '#000000';
  let emissiveIntensity = 0;

  if (isSelected) {
    craneColor = '#67b9ae';
    emissiveColor = '#67b9ae';
    emissiveIntensity = 0.35;
  } else if (hovered) {
    craneColor = '#ffd27d';
    emissiveColor = '#b8860b';
    emissiveIntensity = 0.2;
  } else if (presentationState === 'action_required') {
    craneColor = '#e26e5d';
    emissiveColor = '#d9534f';
    emissiveIntensity = 0.15;
  }

  const metalColor = '#4a5b50';

  const steelMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: craneColor,
        metalness: 0.55,
        roughness: 0.35,
        emissive: emissiveColor,
        emissiveIntensity,
      }),
    [craneColor, emissiveColor, emissiveIntensity],
  );

  const ballastMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: metalColor,
        roughness: 0.85,
      }),
    [metalColor],
  );

  const cabMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#28362d',
        roughness: 0.2,
        metalness: 0.7,
      }),
    [],
  );

  // Cable points
  const hoistLineGeo = useMemo(() => {
    const points = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, -16, 0)];
    return new THREE.BufferGeometry().setFromPoints(points);
  }, []);

  return (
    <group
      position={[-18, 0, -16]}
      onClick={handleSelect}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        onHover?.(craneElem ?? null);
      }}
      onPointerOut={() => {
        setHovered(false);
        onHover?.(null);
      }}
    >
      {/* Concrete foundation ballast pad */}
      <mesh
        position={[0, 0.75, 0]}
        material={ballastMat}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[5, 1.5, 5]} />
      </mesh>

      {/* Cross cruciform steel base */}
      <mesh position={[0, 1.6, 0]} material={steelMat} castShadow>
        <boxGeometry args={[4.2, 0.4, 4.2]} />
      </mesh>

      {/* Main vertical lattice mast */}
      <mesh position={[0, 19, 0]} material={steelMat} castShadow>
        <boxGeometry args={[1.6, 35, 1.6]} />
      </mesh>

      {/* Mast diagonal structural bracing rings */}
      {[8, 16, 24, 32].map((y, idx) => (
        <mesh key={`ring-${idx}`} position={[0, y, 0]} material={ballastMat}>
          <boxGeometry args={[2, 0.4, 2]} />
        </mesh>
      ))}

      {/* Mast outline wireframe */}
      <lineSegments position={[0, 19, 0]}>
        <edgesGeometry args={[new THREE.BoxGeometry(1.6, 35, 1.6)]} />
        <lineBasicMaterial
          color={isSelected ? '#c7fb56' : '#73877b'}
          linewidth={isSelected ? 2 : 1}
        />
      </lineSegments>

      {/* Rotating Upper Slewing Group */}
      <group ref={slewingRef} position={[0, 37.2, 0]}>
        {/* Slewing turntable unit */}
        <mesh position={[0, 0, 0]} material={ballastMat} castShadow>
          <cylinderGeometry args={[1.4, 1.4, 1.2, 12]} />
        </mesh>

        {/* Operator cabin */}
        <mesh position={[1.4, 1, 1.2]} material={cabMat} castShadow>
          <boxGeometry args={[1.8, 2.2, 1.6]} />
        </mesh>

        {/* Top tower apex (A-frame peak) */}
        <mesh position={[0, 4.8, 0]} material={steelMat} castShadow>
          <coneGeometry args={[1.4, 8, 4]} />
        </mesh>

        {/* Main horizontal load jib */}
        <mesh position={[14, 1.4, 0]} material={steelMat} castShadow>
          <boxGeometry args={[28, 1.2, 1.2]} />
        </mesh>

        {/* Jib tie pendants (A-frame to jib) */}
        <mesh
          position={[9, 3.3, 0]}
          rotation={[0, 0, -0.25]}
          material={steelMat}
        >
          <cylinderGeometry args={[0.06, 0.06, 18, 6]} />
        </mesh>

        {/* Counter-jib (rear) */}
        <mesh position={[-7, 1.4, 0]} material={steelMat} castShadow>
          <boxGeometry args={[11, 1.2, 1.2]} />
        </mesh>

        {/* Rear tie pendant */}
        <mesh
          position={[-5, 3.3, 0]}
          rotation={[0, 0, 0.35]}
          material={steelMat}
        >
          <cylinderGeometry args={[0.06, 0.06, 12, 6]} />
        </mesh>

        {/* Concrete counterweight ballast blocks */}
        {[-8, -10].map((cx, idx) => (
          <mesh
            key={`cw-${idx}`}
            position={[cx, 0.4, 0]}
            material={ballastMat}
            castShadow
          >
            <boxGeometry args={[1.8, 1.8, 2.2]} />
          </mesh>
        ))}

        {/* Hoist trolley group (travels along jib) */}
        <group ref={trolleyRef} position={[12, 0.6, 0]}>
          <mesh material={ballastMat}>
            <boxGeometry args={[1.2, 0.5, 1.4]} />
          </mesh>

          {/* Hoist cable wire hanging down */}
          <lineSegments geometry={hoistLineGeo}>
            <lineBasicMaterial color="#ffffff" />
          </lineSegments>

          {/* Hook block */}
          <mesh position={[0, -16.2, 0]} material={steelMat}>
            <boxGeometry args={[0.8, 1.2, 0.8]} />
          </mesh>
        </group>
      </group>
    </group>
  );
}

