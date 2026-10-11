'use client';

import React, { useMemo, useState } from 'react';
import * as THREE from 'three';
import { ThreeEvent } from '@react-three/fiber';
import { SiteElement } from './types';

interface WorkZonesProps {
  onSelect: (element: SiteElement) => void;
  selectedId: string | null;
  elementsMap: Map<string, SiteElement>;
  onHover?: (element: SiteElement | null) => void;
}

interface ZoneMeta {
  id: string;
  position: [number, number, number];
  size: [number, number, number];
  baseThemeColor: string;
}

export const WORK_ZONE_METAS: ZoneMeta[] = [
  {
    id: 'zone-piling',
    position: [24, 0.4, -14],
    size: [18, 0.8, 16],
    baseThemeColor: '#67b9ae',
  },
  {
    id: 'zone-demolition',
    position: [-24, 0.4, 2],
    size: [16, 0.8, 18],
    baseThemeColor: '#e26e5d',
  },
  {
    id: 'zone-material',
    position: [-22, 0.4, -20],
    size: [18, 0.8, 14],
    baseThemeColor: '#edb65b',
  },
  {
    id: 'zone-dust',
    position: [22, 0.4, 18],
    size: [16, 0.8, 14],
    baseThemeColor: '#e26e5d',
  },
  {
    id: 'zone-access',
    position: [0, 0.4, 30],
    size: [32, 0.8, 12],
    baseThemeColor: '#67b9ae',
  },
  {
    id: 'zone-worker',
    position: [28, 0.4, -28],
    size: [14, 0.8, 12],
    baseThemeColor: '#34d399',
  },
  {
    id: 'zone-evidence',
    position: [-30, 0.4, 22],
    size: [12, 0.8, 12],
    baseThemeColor: '#38bdf8',
  },
];

export function WorkZones({
  onSelect,
  selectedId,
  elementsMap,
  onHover,
}: WorkZonesProps) {
  const [hoveredZoneId, setHoveredZoneId] = useState<string | null>(null);

  const boxGeometries = useMemo(() => {
    return WORK_ZONE_METAS.reduce((acc, zone) => {
      acc[zone.id] = new THREE.BoxGeometry(...zone.size);
      return acc;
    }, {} as Record<string, THREE.BoxGeometry>);
  }, []);

  const edgeGeometries = useMemo(() => {
    return WORK_ZONE_METAS.reduce((acc, zone) => {
      acc[zone.id] = new THREE.EdgesGeometry(boxGeometries[zone.id]);
      return acc;
    }, {} as Record<string, THREE.EdgesGeometry>);
  }, [boxGeometries]);

  const handleSelect = (e: ThreeEvent<MouseEvent>, id: string) => {
    e.stopPropagation();
    const elem = elementsMap.get(id);
    if (elem) {
      onSelect(elem);
    }
  };

  return (
    <group>
      {WORK_ZONE_METAS.map((zone) => {
        const elem = elementsMap.get(zone.id);
        const isSelected =
          selectedId === zone.id ||
          (zone.id === 'zone-piling' && selectedId === 'activity-zone') ||
          (zone.id === 'zone-dust' && selectedId === 'dust-zone') ||
          (zone.id === 'zone-demolition' && selectedId === 'restricted-area') ||
          (zone.id === 'zone-worker' && selectedId === 'worker-point') ||
          (zone.id === 'zone-evidence' && selectedId === 'evidence-station');

        const isHovered = hoveredZoneId === zone.id;
        const state = elem?.presentationState ?? 'verified';

        let activeColor = zone.baseThemeColor;
        if (isSelected) {
          activeColor = '#c7fb56'; // high-contrast lime
        } else if (state === 'action_required') {
          activeColor = '#f87171'; // rose
        } else if (state === 'stale') {
          activeColor = '#fbbf24'; // amber
        } else if (state === 'verified') {
          activeColor = '#34d399'; // emerald
        }

        return (
          <group key={zone.id} position={zone.position}>
            {/* Zone floor bounding volume */}
            <mesh
              geometry={boxGeometries[zone.id]}
              onClick={(e) => handleSelect(e, zone.id)}
              onPointerOver={(e) => {
                e.stopPropagation();
                setHoveredZoneId(zone.id);
                onHover?.(elem ?? null);
              }}
              onPointerOut={() => {
                setHoveredZoneId(null);
                onHover?.(null);
              }}
            >
              <meshStandardMaterial
                color={activeColor}
                transparent
                opacity={isSelected ? 0.35 : isHovered ? 0.25 : 0.14}
                roughness={0.7}
                depthWrite={false}
              />
            </mesh>

            {/* Outline boundary lines */}
            <lineSegments geometry={edgeGeometries[zone.id]}>
              <lineBasicMaterial
                color={activeColor}
                linewidth={isSelected ? 2 : 1}
              />
            </lineSegments>

            {/* Corner boundary bollards / markers */}
            {[
              [-zone.size[0] / 2 + 0.3, -zone.size[2] / 2 + 0.3],
              [zone.size[0] / 2 - 0.3, -zone.size[2] / 2 + 0.3],
              [-zone.size[0] / 2 + 0.3, zone.size[2] / 2 - 0.3],
              [zone.size[0] / 2 - 0.3, zone.size[2] / 2 - 0.3],
            ].map(([bx, bz], bIdx) => (
              <mesh key={`bollard-${zone.id}-${bIdx}`} position={[bx, 0.6, bz]}>
                <cylinderGeometry args={[0.18, 0.18, 1.2, 8]} />
                <meshStandardMaterial
                  color={isSelected ? '#c7fb56' : '#fabd48'}
                  roughness={0.4}
                />
              </mesh>
            ))}

            {/* Physical zone details */}
            {zone.id === 'zone-piling' && (
              <group position={[0, 0.4, 0]}>
                <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
                  <ringGeometry args={[2, 2.5, 16]} />
                  <meshBasicMaterial color="#55705e" side={THREE.DoubleSide} />
                </mesh>
              </group>
            )}

            {zone.id === 'zone-access' && (
              <group position={[0, 0.4, 0]}>
                {[-6, -2, 2, 6].map((wx, wIdx) => (
                  <mesh
                    key={`wash-strip-${wIdx}`}
                    position={[wx, 0.05, 0]}
                    rotation={[-Math.PI / 2, 0, 0]}
                  >
                    <planeGeometry args={[1.5, 8]} />
                    <meshStandardMaterial color="#4e6556" roughness={0.7} />
                  </mesh>
                ))}
              </group>
            )}

            {zone.id === 'zone-material' && (
              <group position={[0, 0.4, 0]}>
                {[-4, 4].map((bx, bIdx) => (
                  <mesh key={`bunker-${bIdx}`} position={[bx, 0.8, 0]} castShadow>
                    <boxGeometry args={[4, 1.2, 6]} />
                    <meshStandardMaterial color="#526354" roughness={0.85} />
                  </mesh>
                ))}
              </group>
            )}

            {zone.id === 'zone-worker' && (
              <group position={[0, 0.4, 0]}>
                {/* Muster Point Ring Decal */}
                <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
                  <ringGeometry args={[2.5, 3.0, 24]} />
                  <meshBasicMaterial color="#34d399" side={THREE.DoubleSide} />
                </mesh>
                {/* Shelter canopy roof */}
                <mesh position={[0, 3.2, 0]} castShadow>
                  <boxGeometry args={[6, 0.2, 5]} />
                  <meshStandardMaterial color="#2d4233" roughness={0.6} />
                </mesh>
                {/* 4 Canopy support pillars */}
                {[-2.6, 2.6].map((px, pIdx) =>
                  [-2.1, 2.1].map((pz, zIdx) => (
                    <mesh
                      key={`canopy-col-${pIdx}-${zIdx}`}
                      position={[px, 1.6, pz]}
                    >
                      <cylinderGeometry args={[0.08, 0.08, 3.2, 6]} />
                      <meshStandardMaterial color="#889988" metalness={0.6} />
                    </mesh>
                  )),
                )}
              </group>
            )}

            {zone.id === 'zone-evidence' && (
              <group position={[0, 0.4, 0]}>
                {/* Ground concrete equipment plinth */}
                <mesh position={[0, 0.2, 0]} castShadow>
                  <boxGeometry args={[3.2, 0.4, 3.2]} />
                  <meshStandardMaterial color="#48594e" roughness={0.8} />
                </mesh>
                {/* Telemetry Sensor Mast */}
                <mesh position={[0, 3, 0]} castShadow>
                  <cylinderGeometry args={[0.1, 0.15, 6, 8]} />
                  <meshStandardMaterial color="#829487" metalness={0.7} />
                </mesh>
                {/* Solar panel angled toward south */}
                <mesh
                  position={[0, 4.2, 0.6]}
                  rotation={[-0.6, 0, 0]}
                  castShadow
                >
                  <boxGeometry args={[1.6, 1.2, 0.08]} />
                  <meshStandardMaterial
                    color="#1e3a5f"
                    roughness={0.2}
                    metalness={0.8}
                  />
                </mesh>
                {/* Sensor weather cup anemometer / air sample head */}
                <mesh position={[0, 6.1, 0]}>
                  <sphereGeometry args={[0.3, 12, 12]} />
                  <meshStandardMaterial color="#e2e8f0" metalness={0.5} />
                </mesh>
              </group>
            )}
          </group>
        );
      })}
    </group>
  );
}

