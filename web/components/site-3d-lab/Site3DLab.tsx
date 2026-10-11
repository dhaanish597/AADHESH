'use client';

import React, {
  useState,
  Suspense,
  useEffect,
  useMemo,
  Component,
  ErrorInfo,
  ReactNode,
} from 'react';
import { Canvas } from '@react-three/fiber';
import type { SupervisorPayload } from '@/lib/types';
import { SiteElement, CameraPreset } from './types';
import { resolveSiteElements } from './siteDataBinder';
import { Scene } from './Scene';
import { ContextPanel } from './ContextPanel';
import { WORK_ZONE_METAS } from './WorkZones';
import {
  ArrowsClockwise,
  ArrowsVertical,
  Building,
  Eye,
  Warning,
  ListBullets,
  Cpu,
  CubeFocus,
  Crosshair,
  Play,
  Pause,
  CheckCircle,
  WarningCircle,
  ClockCounterClockwise,
} from '@phosphor-icons/react';

// WebGL Support Detection Helper
function isWebGLAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}

// React Error Boundary for 3D Canvas
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class CanvasErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('3D Control Room Canvas Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// Accessible 2D Fallback Map
function WebGLFallbackView({
  onSelect,
  selectedId,
  elementsMap,
}: {
  onSelect: (elem: SiteElement) => void;
  selectedId: string | null;
  elementsMap: Map<string, SiteElement>;
}) {
  const elements = Array.from(elementsMap.values());

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#0d130f] p-8 text-center text-[#e1ece3]">
      <div className="max-w-md space-y-4">
        <div className="inline-flex p-3 rounded-full bg-amber-950/40 border border-amber-500/30 text-amber-400">
          <Warning size={32} weight="duotone" />
        </div>
        <h3 className="font-mono text-base font-bold text-white">
          WEBGL HARDWARE ACCELERATION UNAVAILABLE
        </h3>
        <p className="text-xs text-slate-400 leading-relaxed">
          WebGL context unavailable. Displaying the accessible 2D schematic control directory below.
        </p>

        {/* 2D Schematic Directory */}
        <div className="p-4 bg-[#141c16] rounded border border-[#243327] space-y-3">
          <span className="font-mono text-[10px] text-emerald-400 font-bold block uppercase tracking-wider">
            SITE SECTORS DIRECTORY ({elements.length} ACTIVE NODES)
          </span>
          <div className="grid grid-cols-2 gap-2 text-left font-mono text-[11px] max-h-64 overflow-y-auto">
            {elements.map((elem) => (
              <button
                key={elem.id}
                onClick={() => onSelect(elem)}
                className={`p-2 rounded border text-left cursor-pointer transition-colors ${
                  selectedId === elem.id
                    ? 'bg-emerald-950/60 border-emerald-400 text-emerald-300'
                    : 'bg-[#1b261f] border-[#293c2e] text-slate-300 hover:text-white'
                }`}
              >
                <div className="truncate font-semibold">{elem.displayName}</div>
                <div className="text-[9px] text-slate-400 uppercase">{elem.presentationState}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export interface Site3DLabProps {
  onElementSelect?: (element: SiteElement | null) => void;
  mode?: 'standalone' | 'embedded';
  className?: string;
  payload?: SupervisorPayload | null;
  selectedId?: string | null;
}

export default function Site3DLab({
  onElementSelect,
  mode = 'standalone',
  className = '',
  payload = null,
  selectedId: propSelectedId,
}: Site3DLabProps) {
  // Derive dynamic map from live backend payload
  const elementsMap = useMemo(() => resolveSiteElements(payload), [payload]);

  const [selectedElement, setSelectedElement] = useState<SiteElement | null>(null);
  const [hoveredElement, setHoveredElement] = useState<SiteElement | null>(null);
  const [explodedView, setExplodedView] = useState(false);
  const [cameraPreset, setCameraPreset] = useState<CameraPreset>('overview');
  const [isCraneAnimated, setIsCraneAnimated] = useState(true);
  const [hasWebGL, setHasWebGL] = useState(true);
  const [showKeyboardList, setShowKeyboardList] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);

  useEffect(() => {
    setHasWebGL(isWebGLAvailable());
  }, []);

  // Synchronize incoming propSelectedId from Supervisor dashboard
  useEffect(() => {
    if (!propSelectedId) {
      return;
    }
    // Match either direct ID or alias mapping
    let matched = elementsMap.get(propSelectedId);
    if (!matched) {
      if (propSelectedId === 'activity-zone') matched = elementsMap.get('zone-piling');
      else if (propSelectedId === 'dust-zone') matched = elementsMap.get('zone-dust');
      else if (propSelectedId === 'restricted-area') matched = elementsMap.get('zone-demolition');
      else if (propSelectedId === 'worker-point') matched = elementsMap.get('zone-worker');
      else if (propSelectedId === 'evidence-station') matched = elementsMap.get('zone-evidence');
      else if (propSelectedId === 'terminal') matched = elementsMap.get('building-main');
    }
    if (matched && matched.id !== selectedElement?.id) {
      setSelectedElement(matched);
      setCameraPreset('focus-selected');
    }
  }, [propSelectedId, elementsMap, selectedElement?.id]);

  const handleSelect = (element: SiteElement | null) => {
    setSelectedElement(element);
    if (element) {
      setPanelOpen(true);
      setCameraPreset('focus-selected');
    }
    if (onElementSelect) {
      onElementSelect(element);
    }
  };

  const handleSelectFloor = (floorIndex: number) => {
    const floorId = `floor-${floorIndex}`;
    const element = elementsMap.get(floorId);
    if (element) {
      handleSelect(element);
    }
  };

  const handleResetCamera = () => {
    setSelectedElement(null);
    setCameraPreset('overview');
    setExplodedView(false);
    onElementSelect?.(null);
  };

  const isEmbedded = mode === 'embedded';

  // Presentation icon for badge
  const getStatusIcon = (state?: string) => {
    if (state === 'action_required') {
      return <WarningCircle weight="fill" className="text-rose-400 text-xs" />;
    }
    if (state === 'stale') {
      return <ClockCounterClockwise weight="fill" className="text-amber-400 text-xs" />;
    }
    return <CheckCircle weight="fill" className="text-emerald-400 text-xs" />;
  };

  return (
    <div
      className={`flex flex-col md:flex-row w-full ${
        isEmbedded
          ? 'bg-[#101612] border-0'
          : 'h-[calc(100vh-68px)] min-h-[580px] bg-[#0c120e]'
      } text-[#e0ede2] select-none font-sans overflow-hidden ${className}`}
      style={isEmbedded ? { height: 580, minHeight: 480 } : undefined}
    >
      {/* 3D Canvas Area */}
      <div
        className={`flex-1 relative ${
          isEmbedded ? 'h-[380px] md:h-full' : 'h-[60vh] md:h-full'
        } bg-[#101512] overflow-hidden`}
      >
        {/* Top Floating Branding & Status */}
        <div className="absolute top-3.5 left-3.5 z-10 flex flex-col gap-1.5 pointer-events-none">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#c7fb56] animate-pulse"></span>
            <h2 className="text-[#eff3e9] font-mono text-[11px] font-bold tracking-widest uppercase">
              {isEmbedded
                ? `SITE OPERATIONS DIGITAL TWIN ${payload ? `[STAGE ${payload.official_stage}]` : ''}`
                : 'AADESH // SITE OPERATIONS DIGITAL TWIN'}
            </h2>
          </div>
          <p className="text-slate-400 font-mono text-[10px] max-w-xs leading-normal bg-[#111713]/85 backdrop-blur-md p-2 rounded border border-[#232f25]">
            Dynamic environmental twin. Click slabs, crane, vehicles, or zones to inspect statutory CAQM obligations.
          </p>
        </div>

        {/* Dynamic Hover Banner Overlay */}
        {hoveredElement && (
          <div className="absolute top-3.5 left-1/2 -translate-x-1/2 z-20 pointer-events-none flex items-center gap-2 bg-[#141d16]/95 backdrop-blur-md px-3 py-1.5 rounded-full border border-emerald-500/40 shadow-lg text-xs font-mono text-white animate-fade-in">
            {getStatusIcon(hoveredElement.presentationState)}
            <span className="font-semibold text-emerald-300">{hoveredElement.displayName}</span>
            <span className="text-slate-400 text-[10px]">
              // {(hoveredElement.presentationState ?? 'verified').toUpperCase()}
            </span>
          </div>
        )}

        {/* Top-Right Control Toolbar */}
        <div className="absolute top-4 right-4 z-10 flex items-center gap-1.5 bg-[#121914]/90 backdrop-blur-md p-1.5 rounded-lg border border-[#233126] shadow-xl">
          {/* Preset Buttons */}
          <button
            onClick={() => setCameraPreset('overview')}
            className={`px-2.5 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              cameraPreset === 'overview'
                ? 'bg-emerald-500 text-[#0c120e]'
                : 'text-slate-300 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Overview Camera View"
          >
            <Eye size={13} />
            <span>OVERVIEW</span>
          </button>

          <button
            onClick={() => setCameraPreset('building')}
            className={`px-2.5 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              cameraPreset === 'building'
                ? 'bg-emerald-500 text-[#0c120e]'
                : 'text-slate-300 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Focus Building"
          >
            <Building size={13} />
            <span>TOWER</span>
          </button>

          <button
            onClick={() => setCameraPreset('crane')}
            className={`px-2.5 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              cameraPreset === 'crane'
                ? 'bg-emerald-500 text-[#0c120e]'
                : 'text-slate-300 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Focus Tower Crane"
          >
            <Cpu size={13} />
            <span>CRANE</span>
          </button>

          {selectedElement && (
            <button
              onClick={() => setCameraPreset('focus-selected')}
              className={`px-2.5 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
                cameraPreset === 'focus-selected'
                  ? 'bg-emerald-500 text-[#0c120e]'
                  : 'text-emerald-300 bg-[#162319] hover:text-white hover:bg-[#1f3024]'
              }`}
              title="Focus Camera on Selected Object"
            >
              <Crosshair size={13} />
              <span>FOCUS</span>
            </button>
          )}

          <div className="h-4 w-px bg-[#263529] mx-1"></div>

          {/* Crane Animation Toggle */}
          <button
            onClick={() => setIsCraneAnimated(!isCraneAnimated)}
            className={`p-1.5 rounded transition-colors cursor-pointer ${
              isCraneAnimated
                ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-600/50'
                : 'text-slate-400 hover:text-white hover:bg-[#1c2720]'
            }`}
            title={
              isCraneAnimated
                ? 'Crane Animation Active (Illustrative)'
                : 'Crane Animation Paused'
            }
          >
            {isCraneAnimated ? <Play size={13} weight="fill" /> : <Pause size={13} />}
          </button>

          {/* Exploded Floors Toggle */}
          <button
            onClick={() => setExplodedView(!explodedView)}
            className={`px-2 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              explodedView
                ? 'bg-emerald-950/70 border border-emerald-400 text-emerald-300'
                : 'text-slate-300 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Exploded Floor View Mode"
          >
            <ArrowsVertical size={13} />
            <span>{explodedView ? 'COLLAPSE' : 'EXPLODED'}</span>
          </button>

          {/* Reset View */}
          <button
            onClick={handleResetCamera}
            className="p-1.5 rounded text-slate-300 hover:text-white hover:bg-[#1c2720] transition-colors cursor-pointer"
            title="Reset Camera & Selection"
          >
            <ArrowsClockwise size={15} />
          </button>

          {/* Accessibility Directory Toggle */}
          <button
            onClick={() => setShowKeyboardList(!showKeyboardList)}
            className={`p-1.5 rounded transition-colors cursor-pointer ${
              showKeyboardList
                ? 'bg-emerald-500 text-black'
                : 'text-slate-300 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Toggle Accessible Element Directory"
            aria-label="Toggle Accessible Element Directory"
          >
            <ListBullets size={15} />
          </button>

          {/* Toggle Inspector Panel */}
          <button
            onClick={() => setPanelOpen(!panelOpen)}
            className={`px-2 py-1.5 rounded font-mono text-[10.5px] font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              panelOpen
                ? 'bg-[#1c2720] text-emerald-300 border border-emerald-500/30'
                : 'text-slate-400 hover:text-white hover:bg-[#1c2720]'
            }`}
            title="Toggle Side Inspector Panel"
          >
            <CubeFocus size={13} />
            <span className="hidden sm:inline">INSPECTOR</span>
          </button>
        </div>

        {/* Keyboard Accessible Element Directory Modal/Tray */}
        {showKeyboardList && (
          <div className="absolute bottom-4 left-4 z-20 max-w-xs w-full bg-[#131b15]/95 backdrop-blur-md p-3.5 rounded-lg border border-[#2b3d30] shadow-2xl space-y-2">
            <div className="flex items-center justify-between border-b border-[#243328] pb-1.5">
              <span className="font-mono text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                ACCESSIBLE SITE ROSTER ({elementsMap.size} ITEMS)
              </span>
              <button
                onClick={() => setShowKeyboardList(false)}
                className="text-slate-400 hover:text-white text-xs cursor-pointer"
              >
                ✕
              </button>
            </div>
            <div className="max-h-60 overflow-y-auto space-y-1 font-mono text-[10.5px]">
              {Array.from(elementsMap.values()).map((elem, idx) => (
                <button
                  key={`acc-${elem.id}`}
                  onClick={() => {
                    handleSelect(elem);
                    setShowKeyboardList(false);
                  }}
                  className={`w-full text-left p-1.5 rounded transition-colors block truncate cursor-pointer ${
                    selectedElement?.id === elem.id
                      ? 'bg-emerald-950/70 border border-emerald-500/50 text-emerald-300'
                      : 'hover:bg-[#202d24] text-slate-200'
                  }`}
                >
                  <span className="text-slate-400 mr-1">{idx + 1}.</span> {elem.displayName}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 3D Canvas with WebGL check and Error Boundary */}
        {!hasWebGL ? (
          <WebGLFallbackView
            onSelect={handleSelect}
            selectedId={selectedElement?.id || null}
            elementsMap={elementsMap}
          />
        ) : (
          <CanvasErrorBoundary
            fallback={
              <WebGLFallbackView
                onSelect={handleSelect}
                selectedId={selectedElement?.id || null}
                elementsMap={elementsMap}
              />
            }
          >
            <Suspense
              fallback={
                <div className="absolute inset-0 flex items-center justify-center bg-[#0d130f] text-emerald-400 font-mono text-xs tracking-widest">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></div>
                    <span>SYNCHRONIZING DIGITAL TWIN WITH BACKEND...</span>
                  </div>
                </div>
              }
            >
              <Canvas
                shadows
                camera={{ position: [48, 38, 48], fov: 32 }}
                gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
                onPointerMissed={() => handleSelect(null)}
              >
                <Scene
                  onSelect={handleSelect}
                  selectedId={selectedElement?.id || null}
                  explodedView={explodedView}
                  cameraPreset={cameraPreset}
                  elementsMap={elementsMap}
                  isCraneAnimated={isCraneAnimated}
                  onHover={setHoveredElement}
                />
              </Canvas>
            </Suspense>
          </CanvasErrorBoundary>
        )}

        {/* Bottom subtle hint bar */}
        <div className="absolute bottom-3 right-4 pointer-events-none text-[10px] font-mono text-slate-400 bg-[#121914]/70 px-2.5 py-1 rounded border border-[#233126]">
          [L-CLICK] Orbit & Select // [R-CLICK] Pan // [SCROLL] Zoom
        </div>
      </div>

      {/* Side Context Panel */}
      {panelOpen && (
        <ContextPanel
          selectedElement={selectedElement}
          onClear={() => handleSelect(null)}
          onSelectFloor={handleSelectFloor}
          explodedView={explodedView}
          onToggleExplodedView={() => setExplodedView(!explodedView)}
          onFocusSelected={() => setCameraPreset('focus-selected')}
          payload={payload}
        />
      )}
    </div>
  );
}

