'use client';

import React, { useMemo, useState } from 'react';
import * as THREE from 'three';
import { ThreeEvent } from '@react-three/fiber';
import { SiteElement } from './types';

interface SiteVehiclesProps {
  onSelect: (element: SiteElement) => void;
  selectedId: string | null;
  elementsMap: Map<string, SiteElement>;
  onHover?: (element: SiteElement | null) => void;
}

export function SiteVehicles({
  onSelect,
  selectedId,
  elementsMap,
  onHover,
}: SiteVehiclesProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // Materials - brightened high-visibility construction colors
  const yellowMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#f2b43b',
        roughness: 0.35,
        metalness: 0.25,
      }),
    [],
  );

  const greenMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#4da773',
        roughness: 0.45,
        metalness: 0.2,
      }),
    [],
  );

  const darkMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#303e35',
        roughness: 0.75,
      }),
    [],
  );

  const cabGlassMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#72ad9e',
        roughness: 0.1,
        metalness: 0.8,
      }),
    [],
  );

  const handleSelectVehicle = (e: ThreeEvent<MouseEvent>, id: string) => {
    e.stopPropagation();
    const elem = elementsMap.get(id);
    if (elem) {
      onSelect(elem);
    }
  };

  const tipperElem = elementsMap.get('vehicle-tipper-1');
  const isTipperSelected = selectedId === 'vehicle-tipper-1';

  const excavatorElem = elementsMap.get('vehicle-excavator-1');
  const isExcavatorSelected = selectedId === 'vehicle-excavator-1';
  const isExcavatorHalted = excavatorElem?.presentationState === 'action_required';

  const sprinklerElem = elementsMap.get('vehicle-sprinkler-1');
  const isSprinklerSelected = selectedId === 'vehicle-sprinkler-1';

  return (
    <group>
      {/* 1. Tipper Truck at Access Road */}
      <group
        position={[6, 0.4, 28]}
        rotation={[0, -Math.PI / 8, 0]}
        onClick={(e) => handleSelectVehicle(e, 'vehicle-tipper-1')}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHoveredId('vehicle-tipper-1');
          onHover?.(tipperElem ?? null);
        }}
        onPointerOut={() => {
          setHoveredId(null);
          onHover?.(null);
        }}
      >
        {/* Chassis */}
        <mesh position={[0, 0.6, 0]} material={darkMat} castShadow>
          <boxGeometry args={[2.4, 0.6, 6]} />
        </mesh>
        {/* Cabin */}
        <mesh
          position={[0, 1.5, 1.8]}
          material={isTipperSelected ? greenMat : yellowMat}
          castShadow
        >
          <boxGeometry args={[2.2, 1.4, 1.8]} />
        </mesh>
        {/* Windshield */}
        <mesh position={[0, 1.6, 2.75]} material={cabGlassMat}>
          <boxGeometry args={[1.8, 0.8, 0.1]} />
        </mesh>
        {/* Tipper Bed Container */}
        <mesh position={[0, 1.6, -1.1]} material={darkMat} castShadow>
          <boxGeometry args={[2.3, 1.4, 3.8]} />
        </mesh>
        {/* Selection wireframe */}
        {isTipperSelected && (
          <lineSegments position={[0, 1.5, 0]}>
            <edgesGeometry args={[new THREE.BoxGeometry(2.6, 2.4, 6.2)]} />
            <lineBasicMaterial color="#c7fb56" linewidth={2} />
          </lineSegments>
        )}
        {/* Wheels */}
        {[-1.2, 1.2].map((x, xIdx) => (
          <group key={`wheels-${xIdx}`}>
            {[-1.8, -0.6, 1.8].map((z, zIdx) => (
              <mesh
                key={`wheel-${xIdx}-${zIdx}`}
                position={[x, 0.4, z]}
                rotation={[0, 0, Math.PI / 2]}
              >
                <cylinderGeometry args={[0.45, 0.45, 0.4, 12]} />
                <meshStandardMaterial color="#171e19" roughness={0.9} />
              </mesh>
            ))}
          </group>
        ))}
      </group>

      {/* 2. Hydraulic Excavator at Demolition Sector */}
      <group
        position={[-23, 0.4, -4]}
        rotation={[0, Math.PI / 4, 0]}
        onClick={(e) => handleSelectVehicle(e, 'vehicle-excavator-1')}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHoveredId('vehicle-excavator-1');
          onHover?.(excavatorElem ?? null);
        }}
        onPointerOut={() => {
          setHoveredId(null);
          onHover?.(null);
        }}
      >
        {/* Crawler Tracks Base */}
        <mesh position={[0, 0.4, 0]} material={darkMat} castShadow>
          <boxGeometry args={[3.2, 0.6, 4.2]} />
        </mesh>
        {/* Slew House / Cab Body */}
        <mesh position={[0, 1.3, 0]} material={yellowMat} castShadow>
          <boxGeometry args={[2.8, 1.2, 3]} />
        </mesh>
        {/* Operator Cab */}
        <mesh position={[0.8, 1.8, 0.6]} material={cabGlassMat}>
          <boxGeometry args={[1, 1, 1.4]} />
        </mesh>
        {/* Counterweight rear */}
        <mesh position={[0, 1.4, -1.3]} material={darkMat} castShadow>
          <boxGeometry args={[2.8, 1, 0.8]} />
        </mesh>
        {/* Boom & Arm */}
        <group position={[-0.4, 1.4, 1.2]} rotation={[0.4, 0, 0]}>
          <mesh position={[0, 1.6, 1.2]} material={yellowMat} castShadow>
            <boxGeometry args={[0.6, 0.6, 3.4]} />
          </mesh>
          <mesh
            position={[0, 2.2, 2.8]}
            rotation={[-0.8, 0, 0]}
            material={darkMat}
            castShadow
          >
            <boxGeometry args={[0.5, 0.5, 2]} />
          </mesh>
        </group>
        {/* Highlight wireframe */}
        {(isExcavatorSelected || isExcavatorHalted) && (
          <lineSegments position={[0, 1.4, 0]}>
            <edgesGeometry args={[new THREE.BoxGeometry(3.6, 2.8, 4.6)]} />
            <lineBasicMaterial
              color={isExcavatorSelected ? '#c7fb56' : '#ff6b6b'}
              linewidth={2}
            />
          </lineSegments>
        )}
      </group>

      {/* 3. Anti-Smog Gun Mist Truck near Dust Zone */}
      <group
        position={[20, 0.4, 8]}
        rotation={[0, -Math.PI / 3, 0]}
        onClick={(e) => handleSelectVehicle(e, 'vehicle-sprinkler-1')}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHoveredId('vehicle-sprinkler-1');
          onHover?.(sprinklerElem ?? null);
        }}
        onPointerOut={() => {
          setHoveredId(null);
          onHover?.(null);
        }}
      >
        {/* Chassis */}
        <mesh position={[0, 0.5, 0]} material={darkMat} castShadow>
          <boxGeometry args={[2.2, 0.5, 5]} />
        </mesh>
        {/* Green Eco Cab */}
        <mesh position={[0, 1.3, 1.6]} material={greenMat} castShadow>
          <boxGeometry args={[2, 1.2, 1.6]} />
        </mesh>
        {/* Water Tank */}
        <mesh
          position={[0, 1.5, -0.8]}
          rotation={[Math.PI / 2, 0, 0]}
          material={greenMat}
          castShadow
        >
          <cylinderGeometry args={[1, 1, 3, 16]} />
        </mesh>
        {/* Anti-Smog Mist Cannon Barrel */}
        <mesh
          position={[0, 2.6, -1]}
          rotation={[-0.3, 0, 0]}
          material={darkMat}
          castShadow
        >
          <cylinderGeometry args={[0.4, 0.6, 1.6, 12]} />
        </mesh>
        {/* Selection wireframe */}
        {isSprinklerSelected && (
          <lineSegments position={[0, 1.5, 0]}>
            <edgesGeometry args={[new THREE.BoxGeometry(2.6, 2.8, 5.4)]} />
            <lineBasicMaterial color="#c7fb56" linewidth={2} />
          </lineSegments>
        )}
      </group>
    </group>
  );
}

