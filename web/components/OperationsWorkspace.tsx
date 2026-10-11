"use client";

import type { SupervisorPayload } from "@/lib/types";
import { formatInstant, stageName } from "@/lib/format";
import { CitationBlock, IconCheck, IconFile, IconUsers } from "@/components/ui";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";

const Site3DLab = dynamic(() => import("@/components/site-3d-lab/Site3DLab"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center bg-[#13181e] border border-[#2c3741] text-[#c7fb56] font-mono text-xs" style={{ height: 560 }}>
      <div className="flex flex-col items-center gap-3">
        <div className="w-7 h-7 border-2 border-[#c7fb56] border-t-transparent rounded-full animate-spin" />
        <span>INITIALIZING 3D SITE DIGITAL TWIN…</span>
      </div>
    </div>
  ),
});

export type SceneObjectKey =
  | "activity-zone"
  | "dust-zone"
  | "restricted-area"
  | "worker-point"
  | "evidence-station"
  | "terminal";

/* ── Metric Card ────────────────────────────────────────────────── */

interface MetricCardProps {
  icon: ReactNode;
  label: string;
  value: number;
  total: number;
  caption: string;
  accent?: "lime" | "teal" | "amber" | "neutral";
}

const ACCENT_CLASSES: Record<string, { bar: string; value: string; glyph: string }> = {
  lime:    { bar: "bg-[#c7fb56]",       value: "text-[#c7fb56]",  glyph: "bg-[#1f2a14] text-[#c7fb56]" },
  teal:    { bar: "bg-[#67b9ae]",       value: "text-[#67b9ae]",  glyph: "bg-[#142523] text-[#67b9ae]" },
  amber:   { bar: "bg-[#edb65b]",       value: "text-[#edb65b]",  glyph: "bg-[#2a2012] text-[#edb65b]" },
  neutral: { bar: "bg-[#879489]",       value: "text-[#b9c4b8]",  glyph: "bg-[#1f272a] text-[#879489]" },
};

function MetricCard({ icon, label, value, total, caption, accent = "neutral" }: MetricCardProps) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  const cls = ACCENT_CLASSES[accent];
  return (
    <div className="metric-card group">
      <div className="flex items-start gap-3">
        <div className={`metric-card-glyph flex-shrink-0 ${cls.glyph}`}>{icon}</div>
        <div className="min-w-0 flex-1">
          <div className="metric-card-label">{label}</div>
          <div className="flex items-baseline gap-1.5 mt-0.5">
            <span className={`metric-card-value ${cls.value}`}>{value}</span>
            {total > 0 && total !== value && (
              <span className="metric-card-total">/ {total}</span>
            )}
          </div>
        </div>
      </div>
      <div className="metric-card-bar-rail">
        <div className={`metric-card-bar-fill ${cls.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="metric-card-caption">{caption}</p>
    </div>
  );
}

/* ── Inspector: maps 3D element ids to real obligations ─────────── */

interface InspectorProps {
  object: SceneObjectKey | null;
  payload: SupervisorPayload | null;
  onClose: () => void;
}

export function SiteObjectInspector({ object, payload, onClose }: InspectorProps) {
  if (!object || !payload) return null;

  const dustObligation =
    payload.obligations.find((o) => o.label.toLowerCase().includes("dust") || o.label.toLowerCase().includes("smog") || o.label.toLowerCase().includes("water")) ?? null;
  const restrictionObligation =
    payload.obligations.find((o) => o.label.toLowerCase().includes("restrict") || o.label.toLowerCase().includes("piling") || o.label.toLowerCase().includes("ban")) ?? null;
  const workerObligation =
    payload.obligations.find((o) => o.issues_parchi) ?? null;

  const openCitation = (sourceDoc: string, page: number, quote: string, hash?: string | null) => (
    <CitationBlock sourceDoc={sourceDoc} page={page} quote={quote} hash={hash} />
  );

  return (
    <aside className="site-inspector" aria-live="polite" aria-labelledby="inspector-title">
      <header className="site-inspector-header">
        <h2 id="inspector-title" className="text-sm font-semibold text-ink">Site inspector</h2>
        <button type="button" onClick={onClose} className="text-xs text-accent hover:text-amber-300 transition-colors" aria-label="Close inspector">
          Close ✕
        </button>
      </header>

      <div className="site-inspector-body">
        {object === "activity-zone" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <svg className="h-4 w-4 text-[#c7fb56]" viewBox="0 0 24 24" fill="none" aria-hidden><rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.6"/><path d="M3 9h18M9 21V9" stroke="currentColor" strokeWidth="1.6"/></svg>
              <p className="text-sm font-medium text-ink">Construction activity zone</p>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              The active site is a piling operation across multiple pits. Dust-generating work here is subject to the invoked GRAP stage and the obligations below.
            </p>
            <dl className="mt-3 space-y-2 text-xs text-dim">
              <div className="kv-row"><span>Site</span><span className="text-ink">{payload.site.label}</span></div>
              <div className="kv-row"><span>Activity</span><span className="text-ink">{payload.site.activity_type ?? "—"}</span></div>
              <div className="kv-row"><span>Category</span><span className="text-ink">{payload.site.project_category ?? "—"}</span></div>
              <div className="kv-row"><span>Stage</span><span className="text-ink">{stageName(payload.official_stage)}</span></div>
            </dl>
          </div>
        )}

        {object === "dust-zone" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <svg className="h-4 w-4 text-[#67b9ae]" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M12 3C12 3 5 10 5 15a7 7 0 0014 0c0-5-7-12-7-12z" stroke="currentColor" strokeWidth="1.6"/></svg>
              <div className="flex items-center justify-between flex-1">
                <p className="text-sm font-medium text-ink">Dust-control measures</p>
                {dustObligation && (
                  <span className={`text-xs font-mono px-1.5 py-0.5 border ${dustObligation.status === "MET" ? "border-[#c7fb56]/40 text-[#c7fb56] bg-[#c7fb56]/10" : "border-[#edb65b]/40 text-[#edb65b] bg-[#edb65b]/10"}`}>
                    {dustObligation.status}
                  </span>
                )}
              </div>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              Dust suppression, water sprinkling, and material-covering obligations apply to the active activity sector.
            </p>
            {dustObligation ? (
              <div className="mt-4 space-y-3">
                <div className="text-sm text-ink">{dustObligation.required_action}</div>
                <div className="text-xs text-faint">{dustObligation.reason}</div>
                {openCitation(dustObligation.source_doc, dustObligation.source_page, dustObligation.source_quote, dustObligation.source_hash)}
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">No dust-control obligation applies to this site profile under the current stage.</p>
            )}
          </div>
        )}

        {object === "restricted-area" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <svg className="h-4 w-4 text-[#edb65b]" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M12 4l9 16H3L12 4z" stroke="currentColor" strokeWidth="1.6"/><path d="M12 10v4M12 17h.01" stroke="currentColor" strokeWidth="1.6"/></svg>
              <p className="text-sm font-medium text-ink">Restricted work area</p>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              Work that is not permitted under the invoked stage is shown with the official condition that governs it.
            </p>
            {restrictionObligation ? (
              <div className="mt-4 space-y-3">
                <div className="text-sm text-ink">{restrictionObligation.required_action}</div>
                <div className="text-xs text-faint">{restrictionObligation.reason}</div>
                {openCitation(restrictionObligation.source_doc, restrictionObligation.source_page, restrictionObligation.source_quote, restrictionObligation.source_hash)}
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">No restriction is imposed by the current obligations for this site.</p>
            )}
          </div>
        )}

        {object === "worker-point" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <IconUsers className="h-4 w-4 text-[#c7fb56]" />
              <p className="text-sm font-medium text-ink">Worker assembly point</p>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              Each rostered worker receives a Parchi — a documented record describing why work is affected. Workers confirm their own record.
            </p>
            <dl className="mt-3 space-y-2 text-xs text-dim">
              <div className="kv-row"><span>Roster size</span><span className="text-ink">{payload.impact.affected}</span></div>
              <div className="kv-row"><span>Parchis issued</span><span className="text-ink">{payload.impact.documented}</span></div>
              <div className="kv-row"><span>Acknowledged</span><span className="text-[#c7fb56] font-mono">{payload.impact.acknowledged}</span></div>
              <div className="kv-row"><span>Awaiting</span><span className="text-[#edb65b]">{payload.impact.documented - payload.impact.acknowledged}</span></div>
              <div className="kv-row"><span>Documentation ready</span><span className="text-ink">{payload.impact.readiness_ready} / {payload.impact.readiness_total}</span></div>
            </dl>
            {workerObligation && (
              <div className="mt-4 text-xs text-faint border-t border-line pt-3">
                Obligation issuing Parchis: <span className="text-ink font-mono">{workerObligation.obligation_id}</span>
              </div>
            )}
          </div>
        )}

        {object === "evidence-station" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <IconFile className="h-4 w-4 text-[#67b9ae]" />
              <p className="text-sm font-medium text-ink">Evidence station</p>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              Every obligation traces back to a verified source document, a cited page, and an exact quotation re-proved against the hashed source bytes.
            </p>
            <a href="/verify" className="mt-4 inline-flex items-center gap-1.5 text-xs text-accent hover:text-amber-300 transition-colors">
              <IconFile className="h-3.5 w-3.5" />
              Open verification lab
            </a>
            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-xs text-faint hover:text-dim">Current stage record</summary>
              <dl className="mt-2 space-y-2 text-xs text-dim">
                <div className="kv-row"><span>Official stage</span><span className="text-ink">{stageName(payload.official_stage)}</span></div>
                <div className="kv-row"><span>Provenance</span><span className="text-ink">{payload.reading ? payload.reading.provenance : "none"}</span></div>
                <div className="kv-row"><span>Reading</span><span className="text-ink">{payload.reading ? `${payload.reading.value} ${payload.reading.parameter}` : "—"}</span></div>
                <div className="kv-row"><span>Observed</span><span className="text-ink">{formatInstant(payload.reading?.observed_at)}</span></div>
                <div className="kv-row"><span>Fully sourced</span><span className="text-ink">{payload.fully_sourced ? "Yes" : "No"}</span></div>
              </dl>
            </details>
          </div>
        )}

        {object === "terminal" && (
          <div className="site-inspector-card">
            <div className="inspector-card-header">
              <svg className="h-4 w-4 text-[#879489]" viewBox="0 0 24 24" fill="none" aria-hidden><rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.6"/><path d="M8 10l3 3-3 3M13 16h4" stroke="currentColor" strokeWidth="1.6"/></svg>
              <p className="text-sm font-medium text-ink">Site operations terminal</p>
            </div>
            <p className="mt-2 text-sm text-dim leading-relaxed">
              The current resolver state, stage detail, and any Standing Order preview.
            </p>
            <details className="mt-4 border border-line bg-panel p-3">
              <summary className="cursor-pointer text-xs text-faint">Resolver state</summary>
              <pre className="mt-2 data text-[11px] text-dim max-h-64 overflow-auto whitespace-pre-wrap">
                {JSON.stringify({ mode: payload.mode, official_stage: payload.official_stage, implied_stage: payload.implied_stage, stage_reason: payload.stage_reason, resolved_at: payload.resolved_at, fully_sourced: payload.fully_sourced }, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </div>
    </aside>
  );
}

/* ── Workflow progress rail ─────────────────────────────────────── */

export function WorkflowProgress({ data }: { data: SupervisorPayload }) {
  const { affected, documented, acknowledged, readiness_ready, readiness_total } = data.impact;

  const nodes = [
    {
      label: "Registered",
      value: affected,
      total: affected,
      detail: `${affected} on roster`,
      caption: "Active roster entries",
      accent: "neutral" as const,
      icon: <IconUsers className="h-3.5 w-3.5" />,
    },
    {
      label: "Parchis issued",
      value: documented,
      total: affected,
      detail: `${affected - documented} still to issue`,
      caption: "Displacement records issued",
      accent: "teal" as const,
      icon: <IconFile className="h-3.5 w-3.5" />,
    },
    {
      label: "Acknowledged",
      value: acknowledged,
      total: documented || 1,
      detail: `${documented - acknowledged} awaiting`,
      caption: "Workers confirmed own record",
      accent: "lime" as const,
      icon: <IconCheck className="h-3.5 w-3.5" />,
    },
    {
      label: "Documentation reviewed",
      value: readiness_ready,
      total: readiness_total || 1,
      detail: `${readiness_total - readiness_ready} to prepare`,
      caption: "Registration paperwork readiness — not an entitlement count",
      accent: "amber" as const,
      icon: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M9 12l2 2 4-4M12 3C8.1 3 5 6.1 5 10c0 3.5 2.2 6.4 5.3 7.5L12 21l1.7-3.5C16.8 16.4 19 13.5 19 10c0-3.9-3.1-7-7-7z" stroke="currentColor" strokeWidth="1.6"/>
        </svg>
      ),
    },
  ];

  return (
    <div className="metric-grid" aria-label="Site acknowledgment progress">
      {nodes.map((n) => (
        <MetricCard
          key={n.label}
          icon={n.icon}
          label={n.label}
          value={n.value}
          total={n.total}
          caption={n.caption}
          accent={n.accent}
        />
      ))}
    </div>
  );
}

/* ── Missions task list ─────────────────────────────────────────── */

export function MissionItem({ title, active, detail }: { title: string; active?: boolean; detail?: string }) {
  return (
    <li className={`mission-item ${active ? "mission-item-active" : ""}`}>
      <div className="mission-item-check" aria-hidden="true">
        <span className="site-scene-dot bg-accent" />
      </div>
      <div>
        <div className="text-sm font-medium text-ink">{title}</div>
        {detail && <div className="text-xs text-dim mt-0.5">{detail}</div>}
      </div>
    </li>
  );
}

/* ── Main OperationsWorkspace ───────────────────────────────────── */

export function OperationsWorkspace({
  payload,
  error,
  busy,
  selectedObject = null,
  onSelectObject,
  children,
}: {
  payload: SupervisorPayload | null;
  error: unknown;
  busy: boolean;
  selectedObject?: string | null;
  onSelectObject?: (object: string | null) => void;
  children?: ReactNode;
}) {
  if (!payload) {
    return (
      <div className="operations-loading">
        <div className="flex items-center gap-2 text-sm text-dim" role="status">
          <span className="h-2.5 w-2.5 rounded-full bg-[#c7fb56] animate-pulse" aria-hidden />
          Resolving site state from verified corpus…
        </div>
      </div>
    );
  }

  const awaitingParchis = payload.impact.documented - payload.impact.acknowledged;

  return (
    <div className="operations-workspace">
      {/* Site header strip */}
      <div className="ops-site-header">
        <div className="ops-site-header-left">
          <div className="ops-site-pip" aria-hidden="true" />
          <div>
            <div className="ops-site-name">{payload.site.label}</div>
            <div className="ops-site-meta">
              {payload.site.activity_type ?? "—"} · {payload.site.project_category ?? "—"}
            </div>
          </div>
        </div>
        <div className="ops-site-header-right">
          <span className={`ops-stage-badge ${payload.official_stage !== "NONE" ? "ops-stage-badge-active" : ""}`}>
            {payload.official_stage !== "NONE" ? `GRAP Stage ${payload.official_stage} — Active replay` : "No active stage invocation"}
          </span>
          <span className="ops-resolved-at">Resolved {formatInstant(payload.resolved_at)}</span>
        </div>
      </div>

      {error ? (
        <div className="operations-error">{String(error)}</div>
      ) : (
        <>
          {/* 3D Digital Twin dynamic visualization */}
          <div className="operations-visualization-area">
            <Site3DLab
              mode="embedded"
              payload={payload}
              selectedId={selectedObject}
              onElementSelect={(elem) => {
                onSelectObject?.(elem?.id ?? null);
              }}
            />
          </div>

          {/* Metric cards */}
          <WorkflowProgress data={payload} />

          {/* Mission task list */}
          <div className="operations-missions">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-ink">Active missions</h2>
              <span className="text-xs text-faint mono">{payload.official_stage !== "NONE" ? "Stage active" : "Standby"}</span>
            </div>
            <ol className="missions-list">
              <MissionItem
                title="Review dust-control obligations"
                active
                detail="Click the dust zone in the 3D twin to see the invoked obligation and its source citation."
              />
              <MissionItem
                title="Review restricted construction activity"
                active
                detail="Check which piling/activity is restricted under the invoked GRAP stage."
              />
              <MissionItem
                title="Complete worker communication"
                active={awaitingParchis > 0}
                detail={awaitingParchis > 0
                  ? `${awaitingParchis} Parchi${awaitingParchis !== 1 ? "s" : ""} await worker acknowledgement.`
                  : "All issued Parchis have been acknowledged."}
              />
              <MissionItem
                title="Inspect evidence provenance"
                active
                detail="Select the evidence station in the 3D twin to follow a citation back to the official source."
              />
            </ol>
          </div>

          {children}
        </>
      )}
    </div>
  );
}
