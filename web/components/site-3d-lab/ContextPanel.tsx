'use client';

import React from 'react';
import type { SupervisorPayload } from '@/lib/types';
import { SiteElement } from './types';
import {
  Building,
  MapPin,
  WarningCircle,
  CheckCircle,
  ClockCounterClockwise,
  Question,
  CubeFocus,
  ArrowsVertical,
  X,
  FileText,
  Users,
  Gauge,
  ShieldCheck,
  Crosshair,
} from '@phosphor-icons/react';

interface ContextPanelProps {
  selectedElement: SiteElement | null;
  onClear: () => void;
  onSelectFloor: (floorIndex: number) => void;
  explodedView: boolean;
  onToggleExplodedView: () => void;
  onFocusSelected?: () => void;
  payload?: SupervisorPayload | null;
}

export function ContextPanel({
  selectedElement,
  onClear,
  onSelectFloor,
  explodedView,
  onToggleExplodedView,
  onFocusSelected,
  payload,
}: ContextPanelProps) {
  const getStateBadge = (state?: string) => {
    switch (state) {
      case 'verified':
        return {
          label: 'VERIFIED // WITHIN GRAP COMPLIANCE',
          bg: 'bg-emerald-950/50 border-emerald-500/40 text-emerald-300',
          icon: <CheckCircle weight="fill" className="text-emerald-400 text-base" />,
        };
      case 'action_required':
        return {
          label: 'ACTION REQUIRED // REMEDIATION FLAGGED',
          bg: 'bg-rose-950/50 border-rose-500/40 text-rose-300',
          icon: <WarningCircle weight="fill" className="text-rose-400 text-base" />,
        };
      case 'stale':
        return {
          label: 'UNAVAILABLE // STALE EVIDENCE (>4h)',
          bg: 'bg-amber-950/50 border-amber-500/40 text-amber-300',
          icon: (
            <ClockCounterClockwise
              weight="fill"
              className="text-amber-400 text-base"
            />
          ),
        };
      default:
        return {
          label: 'NORMAL // NO ACTIVE RESTRICTIONS',
          bg: 'bg-slate-900 border-slate-700/60 text-slate-300',
          icon: <Question weight="bold" className="text-slate-400 text-base" />,
        };
    }
  };

  const badge = getStateBadge(selectedElement?.presentationState);
  const obligation = selectedElement?.obligation;
  const impact = selectedElement?.impactSummary;
  const reading = selectedElement?.readingSummary;

  return (
    <aside className="w-96 flex flex-col h-full bg-[#111713] border-l border-[#243027] text-[#e1ece3] select-none text-xs">
      {/* Header bar */}
      <div className="p-4 border-b border-[#243027] flex items-center justify-between bg-[#151c17]">
        <div className="flex items-center gap-2">
          <CubeFocus weight="duotone" className="text-emerald-400 text-lg" />
          <span className="font-mono tracking-wider font-semibold text-slate-200 uppercase text-[11px]">
            SITE ELEMENT INSPECTOR
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {selectedElement && onFocusSelected && (
            <button
              onClick={onFocusSelected}
              className="p-1 rounded text-slate-400 hover:text-emerald-300 hover:bg-[#202b23] transition-colors flex items-center gap-1 text-[10px] font-mono"
              title="Focus Camera"
              aria-label="Focus Camera"
            >
              <Crosshair size={14} />
              <span className="hidden sm:inline">Focus</span>
            </button>
          )}
          {selectedElement && (
            <button
              onClick={onClear}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-[#202b23] transition-colors"
              title="Clear selection"
              aria-label="Clear selection"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Main Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selectedElement ? (
          <>
            {/* Element Identity */}
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[10px] tracking-widest px-1.5 py-0.5 rounded bg-[#1f2922] text-emerald-300 border border-[#2f3f34] uppercase font-semibold">
                  {selectedElement.type}
                </span>
                {selectedElement.zoneCategory && (
                  <span className="font-mono text-[10px] tracking-wider text-slate-400">
                    // {selectedElement.zoneCategory}
                  </span>
                )}
                {selectedElement.id && (
                  <span className="font-mono text-[9px] text-slate-400 ml-auto">
                    ID: {selectedElement.id}
                  </span>
                )}
              </div>
              <h2 className="text-base font-semibold text-white tracking-tight leading-snug">
                {selectedElement.displayName}
              </h2>
              {selectedElement.floorIdentifier && (
                <div className="flex items-center gap-1.5 text-slate-300 font-mono text-[11px]">
                  <Building size={14} className="text-emerald-400" />
                  <span>Floor Level: {selectedElement.floorIdentifier}</span>
                </div>
              )}
            </div>

            {/* Presentation State Banner */}
            <div className={`p-2.5 rounded border flex items-center gap-2.5 ${badge.bg}`}>
              {badge.icon}
              <div className="flex flex-col">
                <span className="font-mono font-bold tracking-wider text-[10px]">
                  {badge.label}
                </span>
                <span className="text-[10px] opacity-75">
                  Visual state mapping · Non-judicial interface
                </span>
              </div>
            </div>

            {/* Description */}
            {selectedElement.description && (
              <div className="p-3 bg-[#161e18] rounded border border-[#243128] space-y-1">
                <span className="font-mono text-[9px] uppercase tracking-wider text-slate-400 block font-semibold">
                  OPERATIONAL OVERVIEW
                </span>
                <p className="text-slate-300 leading-relaxed text-[11px]">
                  {selectedElement.description}
                </p>
              </div>
            )}

            {/* REAL STATUTORY OBLIGATION DATA (if bound to CAQM corpus) */}
            {obligation && (
              <div className="p-3 bg-[#141d16] rounded border border-emerald-900/60 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-mono text-[10px] font-bold">
                    <FileText size={14} weight="bold" />
                    <span>CAQM STATUTORY OBLIGATION</span>
                  </div>
                  <span
                    className={`font-mono text-[9px] px-1.5 py-0.5 rounded font-semibold ${
                      obligation.status === 'MET'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/50'
                        : obligation.status === 'NOT_MET'
                        ? 'bg-rose-950 text-rose-300 border border-rose-700/50'
                        : 'bg-amber-950 text-amber-300 border border-amber-700/50'
                    }`}
                  >
                    STATUS: {obligation.status}
                  </span>
                </div>

                <div className="text-[11px] font-semibold text-slate-200">
                  {obligation.label}
                </div>

                <div className="text-[10.5px] text-slate-300 space-y-1">
                  <div className="text-emerald-300/90 font-mono text-[9.5px]">
                    REQUIRED ACTION:
                  </div>
                  <p className="bg-[#18231b] p-2 rounded border border-[#26372b] leading-relaxed">
                    {obligation.required_action}
                  </p>
                </div>

                {obligation.reason && (
                  <div className="text-[10px] text-slate-400 leading-normal">
                    <span className="text-slate-300 font-mono text-[9.5px]">REASON: </span>
                    {obligation.reason}
                  </div>
                )}

                {/* Source Citation & Hash */}
                <div className="pt-2 border-t border-[#233327] space-y-1 font-mono text-[9.5px]">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>SOURCE DOCUMENT</span>
                    <span className="text-slate-300">{obligation.source_doc} (p.{obligation.source_page})</span>
                  </div>
                  {obligation.source_quote && (
                    <blockquote className="italic text-slate-400 text-[9.5px] border-l-2 border-emerald-600/60 pl-2 my-1">
                      "{obligation.source_quote}"
                    </blockquote>
                  )}
                  {obligation.source_hash && (
                    <div className="flex items-center gap-1 text-[9px] text-emerald-400/80 truncate">
                      <ShieldCheck size={12} weight="bold" />
                      <span className="font-mono">HASH: {obligation.source_hash.slice(0, 16)}...</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* REAL WORKER IMPACT DATA (for zone-worker) */}
            {impact && (
              <div className="p-3 bg-[#141e17] rounded border border-emerald-900/50 space-y-2">
                <div className="flex items-center gap-1.5 text-emerald-400 font-mono text-[10px] font-bold">
                  <Users size={14} weight="bold" />
                  <span>WORKFORCE ROSTER & PARCHI RECORDS</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-center font-mono">
                  <div className="p-2 rounded bg-[#19241d] border border-[#26372b]">
                    <div className="text-[9px] text-slate-400">AFFECTED</div>
                    <div className="text-sm font-bold text-slate-100">{impact.affected}</div>
                  </div>
                  <div className="p-2 rounded bg-[#19241d] border border-[#26372b]">
                    <div className="text-[9px] text-slate-400">PARCHIS ISSUED</div>
                    <div className="text-sm font-bold text-emerald-300">{impact.documented}</div>
                  </div>
                  <div className="p-2 rounded bg-[#19241d] border border-[#26372b]">
                    <div className="text-[9px] text-slate-400">ACKNOWLEDGED</div>
                    <div className="text-sm font-bold text-emerald-400">{impact.acknowledged}</div>
                  </div>
                  <div className="p-2 rounded bg-[#19241d] border border-[#26372b]">
                    <div className="text-[9px] text-slate-400">AWAITING</div>
                    <div className="text-sm font-bold text-amber-300">{impact.awaiting}</div>
                  </div>
                </div>
                <div className="flex justify-between items-center text-[10px] font-mono pt-1 text-slate-400">
                  <span>READINESS COMPLIANCE</span>
                  <span className="text-emerald-300">
                    {impact.readinessReady} / {impact.readinessTotal} READY
                  </span>
                </div>
              </div>
            )}

            {/* REAL READING / SENSOR DATA (for zone-evidence) */}
            {reading && (
              <div className="p-3 bg-[#131b1f] rounded border border-sky-900/50 space-y-2">
                <div className="flex items-center gap-1.5 text-sky-400 font-mono text-[10px] font-bold">
                  <Gauge size={14} weight="bold" />
                  <span>ENVIRONMENTAL TELEMETRY & PROVENANCE</span>
                </div>
                <div className="font-mono text-[10.5px] space-y-1.5">
                  <div className="flex justify-between py-0.5 border-b border-[#1e2d36]">
                    <span className="text-slate-400">STATION ID</span>
                    <span className="text-sky-300">{reading.stationId}</span>
                  </div>
                  <div className="flex justify-between py-0.5 border-b border-[#1e2d36]">
                    <span className="text-slate-400">MEASURED VALUE</span>
                    <span className="text-sky-200 font-bold">
                      {reading.parameter}: {reading.value} µg/m³
                    </span>
                  </div>
                  <div className="flex justify-between py-0.5 border-b border-[#1e2d36]">
                    <span className="text-slate-400">PROVENANCE</span>
                    <span className="text-slate-200 uppercase">{reading.provenance}</span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <span className="text-slate-400">FRESHNESS</span>
                    <span
                      className={
                        reading.freshness === 'FRESH'
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }
                    >
                      {reading.freshness ?? 'FRESH'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Element Details & Attributes */}
            {selectedElement.details && (
              <div className="p-3 bg-[#161e18] rounded border border-[#243128] space-y-2">
                <span className="font-mono text-[9px] uppercase tracking-wider text-slate-400 block font-semibold">
                  SITE TELEMETRY & ATTRIBUTES
                </span>
                <div className="grid grid-cols-1 gap-1.5 font-mono text-[10px]">
                  {selectedElement.details.location && (
                    <div className="flex justify-between py-0.5 border-b border-[#212c24]">
                      <span className="text-slate-400">LOCATION</span>
                      <span className="text-slate-200">{selectedElement.details.location}</span>
                    </div>
                  )}
                  {selectedElement.details.equipmentCount !== undefined && (
                    <div className="flex justify-between py-0.5 border-b border-[#212c24]">
                      <span className="text-slate-400">ASSET COUNT</span>
                      <span className="text-emerald-400 font-semibold">
                        {selectedElement.details.equipmentCount} UNITS
                      </span>
                    </div>
                  )}
                  {selectedElement.details.lastInspection && (
                    <div className="flex justify-between py-0.5 border-b border-[#212c24]">
                      <span className="text-slate-400">SYNC STATUS</span>
                      <span className="text-slate-300">{selectedElement.details.lastInspection}</span>
                    </div>
                  )}
                  {selectedElement.details.statusNote && (
                    <div className="pt-1 text-[10px] text-amber-300/90 leading-tight">
                      * {selectedElement.details.statusNote}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Provenance and Integrity Label */}
            <div className="p-2.5 bg-[#121914] rounded border border-[#212d23] text-[9.5px] font-mono text-slate-400">
              <span className="text-slate-300 font-semibold">DATA INTEGRITY NOTE:</span>{' '}
              {payload ? (
                <span>
                  Correlated with live Aadesh resolver payload (Site: {payload.site_id}, Stage: {payload.official_stage}).
                </span>
              ) : (
                <span>
                  Viewing local test model. Backend connection offline or standalone harness active.
                </span>
              )}
            </div>
          </>
        ) : (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 space-y-3 text-slate-400">
            <div className="w-12 h-12 rounded-full bg-[#172019] border border-[#263529] flex items-center justify-center text-slate-500">
              <MapPin size={24} weight="duotone" />
            </div>
            <div>
              <p className="font-mono text-slate-300 text-xs font-semibold mb-1">
                NO ELEMENT SELECTED
              </p>
              <p className="text-[11px] text-slate-400 max-w-[220px] leading-relaxed">
                Click any building slab, tower crane, vehicle, or boundary work zone in the 3D twin to inspect its live state and obligations.
              </p>
            </div>
          </div>
        )}

        {/* Level & Exploded View Selector */}
        <div className="pt-2 border-t border-[#232f26] space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
              BUILDING FLOOR SELECTOR
            </span>
            <button
              onClick={onToggleExplodedView}
              className={`flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                explodedView
                  ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300 font-semibold'
                  : 'bg-[#18211b] border-[#29382d] text-slate-400 hover:text-slate-200'
              }`}
            >
              <ArrowsVertical size={11} />
              <span>{explodedView ? 'COLLAPSE' : 'EXPLODED'}</span>
            </button>
          </div>

          <div className="grid grid-cols-5 gap-1.5">
            {[4, 3, 2, 1, 0].map((floor) => {
              const floorId = `floor-${floor}`;
              const isSelected = selectedElement?.id === floorId;
              return (
                <button
                  key={`floor-btn-${floor}`}
                  onClick={() => onSelectFloor(floor)}
                  className={`py-1.5 rounded font-mono text-[11px] font-bold border transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-emerald-500 text-[#0c120e] border-emerald-400 shadow-sm'
                      : 'bg-[#161e18] text-slate-300 border-[#263529] hover:bg-[#202b22] hover:text-white'
                  }`}
                >
                  L{floor}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Safety Notice Footer */}
      <div className="p-3 bg-[#0d120f] border-t border-[#202b23] text-[9.5px] font-mono text-slate-400 leading-tight">
        <span className="text-amber-400 font-semibold">AADESH DIGITAL TWIN</span> // Elements reflect statutory compliance states without modifying official enforcement records.
      </div>
    </aside>
  );
}

