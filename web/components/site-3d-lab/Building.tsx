'use client';

import React, { useMemo, useState } from 'react';
import * as THREE from 'three';
import { ThreeEvent } from '@react-three/fiber';
import { SiteElement } from './types';

interface BuildingProps {
  onSelect: (element: SiteElement) => void;
  selectedId: string | null;
  explodedView: boolean;
  elementsMap: Map<string, SiteElement>;
  onHover?: (element: SiteElement | null) => void;
}

export const FLOOR_COUNT = 5;
const BASE_FLOOR_HEIGHT = 4.2;
const EXPLODED_GAP = 3.6;
const BUILDING_WIDTH = 28;
const BUILDING_DEPTH = 18;

export function Building({
  onSelect,
  selectedId,
  explodedView,
  elementsMap,
  onHover,
}: BuildingProps) {
  const [hoveredFloor, setHoveredFloor] = useState<number | null>(null);
  const [hoveredBuilding, setHoveredBuilding] = useState(false);

  // Reusable architectural concrete & steel materials
  const concreteMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#5a6b60',
        roughness: 0.78,
        metalness: 0.1,
      }),
    [],
  );

  const coreMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#49584e',
        roughness: 0.82,
        metalness: 0.08,
      }),
    [],
  );

  const rebarMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#c27a4b',
        roughness: 0.45,
        metalness: 0.75,
      }),
    [],
  );

  const safetyNetMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#349365',
        roughness: 0.5,
        transparent: true,
        opacity: 0.7,
        wireframe: true,
      }),
    [],
  );

  const handleFloorClick = (e: ThreeEvent<MouseEvent>, floorIndex: number) => {
    e.stopPropagation();
    const elem = elementsMap.get(`floor-${floorIndex}`);
    if (elem) {
      onSelect(elem);
    }
  };

  const handleBuildingClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const elem = elementsMap.get('building-main');
    if (elem) {
      onSelect(elem);
    }
  };

  // Pre-calculate column offsets
  const columnPositions = useMemo(() => {
    const xOffsets = [-BUILDING_WIDTH / 2 + 2, 0, BUILDING_WIDTH / 2 - 2];
    const zOffsets = [-BUILDING_DEPTH / 2 + 2, BUILDING_DEPTH / 2 - 2];
    const coords: [number, number][] = [];
    for (const x of xOffsets) {
      for (const z of zOffsets) {
        coords.push([x, z]);
      }
    }
    return coords;
  }, []);

  return (
    <group position={[0, 0, 0]}>
      {/* Central core elevator shaft (spans up the building) */}
      <mesh
        position={[0, (FLOOR_COUNT * BASE_FLOOR_HEIGHT) / 2, 0]}
        material={coreMat}
        castShadow
        receiveShadow
        onClick={handleBuildingClick}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHoveredBuilding(true);
          onHover?.(elementsMap.get('building-main') ?? null);
        }}
        onPointerOut={() => {
          setHoveredBuilding(false);
          onHover?.(null);
        }}
      >
        <boxGeometry args={[7, FLOOR_COUNT * BASE_FLOOR_HEIGHT + 2, 6]} />
      </mesh>

      {/* Floors array */}
      {Array.from({ length: FLOOR_COUNT }).map((_, i) => {
        const floorId = `floor-${i}`;
        const floorElem = elementsMap.get(floorId);
        const yOffset = explodedView
          ? i * (BASE_FLOOR_HEIGHT + EXPLODED_GAP)
          : i * BASE_FLOOR_HEIGHT;

        const isSelected = selectedId === floorId;
        const isHovered = hoveredFloor === i;
        const isParentSelected = selectedId === 'building-main';

        // State-driven color styling
        const presentationState = floorElem?.presentationState ?? 'verified';
        let baseColor = '#627368';
        let emissiveColor = '#000000';
        let emissiveIntensity = 0;

        if (isSelected) {
          baseColor = '#67b9ae';
          emissiveColor = '#67b9ae';
          emissiveIntensity = 0.38;
        } else if (isHovered) {
          baseColor = '#809688';
          emissiveColor = '#3a5245';
          emissiveIntensity = 0.2;
        } else if (isParentSelected) {
          baseColor = '#728579';
        } else if (presentationState === 'action_required') {
          baseColor = '#7c5e58';
          emissiveColor = '#d9534f';
          emissiveIntensity = 0.15;
        } else if (presentationState === 'stale') {
          baseColor = '#7a7058';
          emissiveColor = '#d39e38';
          emissiveIntensity = 0.12;
        }

        return (
          <group key={floorId} position={[0, yOffset, 0]}>
            {/* Slab */}
            <mesh
              position={[0, 0, 0]}
              castShadow
              receiveShadow
              onClick={(e) => handleFloorClick(e, i)}
              onPointerOver={(e) => {
                e.stopPropagation();
                setHoveredFloor(i);
                onHover?.(floorElem ?? null);
              }}
              onPointerOut={() => {
                setHoveredFloor(null);
                onHover?.(null);
              }}
            >
              <boxGeometry args={[BUILDING_WIDTH, 0.5, BUILDING_DEPTH]} />
              <meshStandardMaterial
                color={baseColor}
                emissive={emissiveColor}
                emissiveIntensity={emissiveIntensity}
                roughness={0.72}
                metalness={0.14}
              />
            </mesh>

            {/* Slab edge wireframe for clean architectural silhouette */}
            <lineSegments position={[0, 0, 0]}>
              <edgesGeometry
                args={[new THREE.BoxGeometry(BUILDING_WIDTH, 0.5, BUILDING_DEPTH)]}
              />
              <lineBasicMaterial
                color={
                  isSelected
                    ? '#c7fb56'
                    : isHovered
                    ? '#ffffff'
                    : presentationState === 'action_required'
                    ? '#ff6b6b'
                    : '#8ea396'
                }
                linewidth={isSelected ? 2 : 1}
              />
            </lineSegments>

            {/* Structural columns supporting this floor to the next */}
            {i < FLOOR_COUNT - 1 && (
              <group position={[0, BASE_FLOOR_HEIGHT / 2, 0]}>
                {columnPositions.map(([cx, cz], colIdx) => (
                  <mesh
                    key={`col-${i}-${colIdx}`}
                    position={[cx, 0, cz]}
                    material={concreteMat}
                    castShadow
                    receiveShadow
                    onClick={handleBuildingClick}
                  >
                    <boxGeometry args={[1.4, BASE_FLOOR_HEIGHT - 0.5, 1.4]} />
                  </mesh>
                ))}

                {/* Safety green net on active work decks (Level 2 & 3) */}
                {(i === 2 || i === 3) && (
                  <mesh
                    position={[0, 0, BUILDING_DEPTH / 2 - 0.2]}
                    material={safetyNetMat}
                  >
                    <boxGeometry
                      args={[BUILDING_WIDTH - 2, BASE_FLOOR_HEIGHT - 1, 0.1]}
                    />
                  </mesh>
                )}
              </group>
            )}

            {/* Top floor rebar starter bars sticking out on top slab */}
            {i === FLOOR_COUNT - 1 && (
              <group position={[0, 1.2, 0]}>
                {columnPositions.map(([cx, cz], rIdx) => (
                  <mesh
                    key={`rebar-${rIdx}`}
                    position={[cx, 0, cz]}
                    material={rebarMat}
                  >
                    <cylinderGeometry args={[0.08, 0.08, 2, 6]} />
                  </mesh>
                ))}
              </group>
            )}
          </group>
        );
      })}
    </group>
  );
}

