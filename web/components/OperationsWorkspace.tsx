"use client";

import type { SupervisorPayload } from "@/lib/types";
import { formatInstant, stageName } from "@/lib/format";
import { CitationBlock, IconCheck, IconFile, IconUsers } from "@/components/ui";
import type { ReactNode } from "react";

export type SceneObjectKey =
  | "activity-zone"
  | "dust-zone"
  | "restricted-area"
  | "worker-point"
  | "evidence-station"
  | "terminal";

interface SceneObjectProps {
  key: SceneObjectKey;
  selected: boolean;
  onClick: () => void;
  label: string;
  status: "active" | "idle" | "warn" | "unknown";
  description: string;
}

function SceneObject({
  selected,
  onClick,
  label,
  status,
}: SceneObjectProps) {
  const statusMark =
    status === "active" ? "bg-success" : status === "warn" ? "bg-accent" : status === "unknown" ? "bg-info" : "bg-faint";
  return (
    <g
      className={`site-object ${selected ? "site-object-selected" : ""}`}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      aria-label={label}
    >
      <rect
        x={0}
        y={0}
        width={64}
        height={64}
        className={`site-object-bg ${statusMark}`}
        rx={10}
        strokeWidth={1.4}
      />
      <text
        y={34}
        className="site-object-mark"
        textAnchor="middle"
        fontSize={22}
      >
        {label[0].toUpperCase()}
      </text>
      <text
        x={32}
        y={58}
        className="site-object-label"
        textAnchor="middle"
        fontSize={9}
      >
        {label.toUpperCase()}
      </text>
    </g>
  );
}

interface ProgressNodeProps {
  title: string;
  value: number;
  total: number;
  detail: string;
  selected: boolean;
  onClick: () => void;
}

function ProgressNode({ title, value, total, detail, selected, onClick }: ProgressNodeProps) {
  const percent = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`progress-node ${selected ? "progress-node-selected" : ""}`}
      aria-pressed={selected}
    >
      <div className="progress-node-glyph">
        {value >= total ? (
          <IconCheck className="h-4 w-4" />
        ) : (
          <span className="progress-node-count">{value}</span>
        )}
      </div>
      <div className="progress-node-meta">
        <div className="progress-node-label">{title}</div>
        <div className="progress-node-detail">{detail}</div>
      </div>
      <div className="progress-node-bar" aria-hidden="true">
        <span className="progress-node-fill" style={{ width: `${percent}%` }} />
      </div>
    </button>
  );
}

interface WorkflowProgressProps {
  data: SupervisorPayload;
}

export function WorkflowProgress({ data }: WorkflowProgressProps) {
  const registered = data.impact.affected;
  const issued = data.impact.documented;
  const acknowledged = data.impact.acknowledged;
  const reviewed = data.impact.readiness_ready;

  return (
    <div className="workflow-progress" aria-label="Site acknowledgment progress">
      <div className="workflow-progress-rail">
        {[
          { title: "Registered", value: registered, total: registered, detail: `${registered} on roster` },
          { title: "Parchis issued", value: issued, total: registered, detail: `${registered - issued} still to issue` },
          { title: "Acknowledged", value: acknowledged, total: issued, detail: `${issued - acknowledged} awaiting confirmation` },
          { title: "Documentation reviewed", value: reviewed, total: data.impact.readiness_total, detail: `${data.impact.readiness_total - reviewed} to prepare` },
        ].map((node) => (
          <ProgressNode
            key={node.title}
            title={node.title}
            value={node.value}
            total={node.total}
            detail={node.detail}
            selected={false}
            onClick={() => {}}
          />
        ))}
      </div>
      <p className="text-xs text-faint">
        Documentation readiness measures registration paperwork, not entitlement. No sum is computed from these counts.
      </p>
    </div>
  );
}

interface InspectorProps {
  object: SceneObjectKey | null;
  payload: SupervisorPayload | null;
  onClose: () => void;
}

export function SiteObjectInspector({ object, payload, onClose }: InspectorProps) {
  if (!object || !payload) return null;

  const openCitation = (
    sourceDoc: string,
    page: number,
    quote: string,
    hash?: string | null,
  ) => (
    <CitationBlock sourceDoc={sourceDoc} page={page} quote={quote} hash={hash} />
  );

  const dustObligation =
    payload.obligations.find((o) => o.label.toLowerCase().includes("dust")) ??
    null;
  const restrictionObligation =
    payload.obligations.find((o) => o.label.toLowerCase().includes("restrict")) ??
    null;
  const workerObligation =
    payload.obligations.find((o) => o.issues_parchi) ??
    null;

  return (
    <aside className="site-inspector" aria-live="polite" aria-labelledby="inspector-title">
      <header className="site-inspector-header">
        <h2 id="inspector-title" className="text-sm font-semibold text-ink">
          Site inspector
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-accent"
          aria-label="Close inspector"
        >
          Close
        </button>
      </header>

      <div className="site-inspector-body">
        {object === "activity-zone" && (
          <div className="site-inspector-card">
            <p className="text-sm font-medium text-ink">Construction activity zone</p>
            <p className="mt-2 text-sm text-dim">
              The active site is a piling operation across multiple pits. Dust-generating work
              here is subject to the invoked GRAP stage and the obligations below.
            </p>
            <dl className="mt-3 space-y-2 text-xs text-dim">
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Site</span>
                <span className="text-ink">{payload.site.label}</span>
              </div>
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Activity</span>
                <span className="text-ink">{payload.site.activity_type ?? "—"}</span>
              </div>
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Category</span>
                <span className="text-ink">{payload.site.project_category ?? "—"}</span>
              </div>
            </dl>
          </div>
        )}

        {object === "dust-zone" && (
          <div className="site-inspector-card">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">Dust-control measures</p>
              {dustObligation ? (
                <span className="text-xs text-faint">
                  {dustObligation.status}
                </span>
              ) : (
                <span className="text-xs text-faint">No applicable clause</span>
              )}
            </div>
            <p className="mt-2 text-sm text-dim">
              Dust suppression, water sprinkling, and material-covering obligations apply to the
              active activity sector. Inspect the cited source to see the exact wording.
            </p>
            {dustObligation ? (
              <div className="mt-4 space-y-3">
                <div className="text-sm text-ink">{dustObligation.required_action}</div>
                <div className="text-xs text-faint">{dustObligation.reason}</div>
                {openCitation(
                  dustObligation.source_doc,
                  dustObligation.source_page,
                  dustObligation.source_quote,
                  dustObligation.source_hash,
                )}
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">
                No dust-control obligation applies to this site profile under the current stage.
              </p>
            )}
          </div>
        )}

        {object === "restricted-area" && (
          <div className="site-inspector-card">
            <p className="text-sm font-medium text-ink">Restricted work area</p>
            <p className="mt-2 text-sm text-dim">
              Work that is not permitted under the invoked stage is shown here with the official
              condition that governs it.
            </p>
            {restrictionObligation ? (
              <div className="mt-4 space-y-3">
                <div className="text-sm text-ink">{restrictionObligation.required_action}</div>
                <div className="text-xs text-faint">{restrictionObligation.reason}</div>
                {openCitation(
                  restrictionObligation.source_doc,
                  restrictionObligation.source_page,
                  restrictionObligation.source_quote,
                  restrictionObligation.source_hash,
                )}
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">
                No restriction is imposed by the current obligations for this site.
              </p>
            )}
          </div>
        )}

        {object === "worker-point" && (
          <div className="site-inspector-card">
            <div className="flex items-center gap-2">
              <IconUsers className="h-4 w-4 text-accent" />
              <p className="text-sm font-medium text-ink">Worker assembly point</p>
            </div>
            <p className="mt-2 text-sm text-dim">
              Each rostered worker receives a Parchi describing why work is affected and the
              sources behind it. Workers confirm their own record.
            </p>
            <dl className="mt-3 space-y-2 text-xs text-dim">
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Parchis issued</span>
                <span className="text-ink">{payload.impact.documented}</span>
              </div>
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Acknowledged</span>
                <span className="text-ink">{payload.impact.acknowledged}</span>
              </div>
              <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                <span>Awaiting</span>
                <span className="text-ink">{payload.impact.documented - payload.impact.acknowledged}</span>
              </div>
            </dl>
            {workerObligation && (
              <div className="mt-4 text-xs text-faint">
                Example obligation that issues a Parchi: {workerObligation.obligation_id}
              </div>
            )}
          </div>
        )}

        {object === "evidence-station" && (
          <div className="site-inspector-card">
            <p className="text-sm font-medium text-ink">Evidence station</p>
            <p className="mt-2 text-sm text-dim">
              Every obligation above traces back to a verified source document, a cited page, and an
              exact quotation. Open the verification lab to re-prove the whole corpus.
            </p>
            <a
              href="/verify"
              className="mt-4 inline-flex items-center gap-1 text-xs text-accent"
            >
              <IconFile className="h-3.5 w-3.5" />
              Open verification lab
            </a>
            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-xs text-faint">
                Current stage record
              </summary>
              <dl className="mt-2 space-y-2 text-xs text-dim">
                <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                  <span>Official stage</span>
                  <span className="text-ink">{stageName(payload.official_stage)}</span>
                </div>
                <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                  <span>Provenance</span>
                  <span className="text-ink">
                    {payload.reading ? payload.reading.provenance : "none"}
                  </span>
                </div>
                <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                  <span>Reading</span>
                  <span className="text-ink">
                    {payload.reading
                      ? `${payload.reading.value} ${payload.reading.parameter}`
                      : "—"}
                  </span>
                </div>
                <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2">
                  <span>Observed</span>
                  <span className="text-ink">{formatInstant(payload.reading?.observed_at)}</span>
                </div>
              </dl>
            </details>
          </div>
        )}

        {object === "terminal" && (
          <div className="site-inspector-card">
            <p className="text-sm font-medium text-ink">Site operations terminal</p>
            <p className="mt-2 text-sm text-dim">
              The current resolver state, stage detail, and any Standing Order preview live here.
            </p>
            <details className="mt-4 border border-line bg-panel p-3">
              <summary className="cursor-pointer text-xs text-faint">
                Resolver state
              </summary>
              <pre className="mt-2 data text-[11px] text-dim max-h-64 overflow-auto">
                {JSON.stringify(
                  {
                    mode: payload.mode,
                    official_stage: payload.official_stage,
                    implied_stage: payload.implied_stage,
                    stage_reason: payload.stage_reason,
                    resolved_at: payload.resolved_at,
                    fully_sourced: payload.fully_sourced,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
        )}
      </div>
    </aside>
  );
}

export function SiteScene({
  selectedObject,
  onSelectObject,
}: {
  selectedObject: SceneObjectKey | null;
  onSelectObject: (key: SceneObjectKey) => void;
}) {
  const objects: { key: SceneObjectKey; x: number; y: number; label: string; status: SceneObjectProps["status"] }[] = [
    { key: "activity-zone", x: 80, y: 300, label: "Activity zone", status: "active" },
    { key: "dust-zone", x: 220, y: 220, label: "Dust zone", status: "active" },
    { key: "restricted-area", x: 370, y: 320, label: "Restricted area", status: "warn" },
    { key: "worker-point", x: 520, y: 240, label: "Worker point", status: "idle" },
    { key: "evidence-station", x: 640, y: 340, label: "Evidence", status: "idle" },
    { key: "terminal", x: 120, y: 120, label: "Terminal", status: "idle" },
  ];

  return (
    <div className="site-scene" aria-label="Interactive site map">
      <div className="site-scene-surface" aria-hidden="true">
        <svg
          viewBox="0 0 720 440"
          className="site-scene-svg"
          role="img"
          aria-label="Illustrative construction site map"
        >
          <defs>
            <linearGradient id="sitePlatform" x1="120" y1="320" x2="620" y2="400" gradientUnits="userSpaceOnUse">
              <stop stopColor="#243a32" />
              <stop offset="1" stopColor="#111b19" />
            </linearGradient>
            <pattern id="siteGrid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M24 0H0V24" stroke="#c3d8cc" strokeOpacity="0.08" />
            </pattern>
          </defs>

          <path
            d="M120 320 L540 320 L600 392 L160 392 Z"
            fill="url(#sitePlatform)"
            stroke="#496057"
            strokeWidth={1.2}
          />
          <path
            d="M138 336 L522 336 L576 380 L168 380 Z"
            fill="url(#siteGrid)"
            stroke="#9db0a2"
            strokeOpacity="0.22"
          />

          {/* access path */}
          <path
            d="M120 352 H540"
            stroke="#1b271f"
            strokeWidth={14}
            strokeLinecap="round"
          />
          <path
            d="M120 352 H540"
            stroke="#c7fb56"
            strokeWidth={3}
            strokeLinecap="round"
            strokeDasharray="5 10"
            opacity={0.7}
          />

          {/* site objects */}
          {objects.map((obj) => (
            <g
              key={obj.key}
              transform={`translate(${obj.x - 32}, ${obj.y - 32})`}
            >
              <SceneObject
                key={obj.key}
                selected={selectedObject === obj.key}
                onClick={() => onSelectObject(obj.key)}
                label={obj.label}
                status={obj.status}
                description=""
              />
            </g>
          ))}

          {/* small scene detail dots */}
          <circle cx="300" cy="360" r="2" fill="#c7fb56" />
          <circle cx="430" cy="372" r="1.5" fill="#a8e4b3" />
          <circle cx="510" cy="360" r="1.5" fill="#a8e4b3" />
        </svg>
      </div>
      <div className="site-scene-legend">
        <span className="site-scene-legend-item">
          <span className="site-scene-dot bg-success" /> Active
        </span>
        <span className="site-scene-legend-item">
          <span className="site-scene-dot bg-accent" /> Needs attention
        </span>
        <span className="site-scene-legend-item">
          <span className="site-scene-dot bg-faint" /> Idle
        </span>
      </div>
    </div>
  );
}

export function OperationsWorkspace({
  payload,
  error,
  children,
}: {
  payload: SupervisorPayload | null;
  error: unknown;
  busy: boolean;
  children?: ReactNode;
}) {
  if (!payload) {
    return <div className="operations-loading">Resolving site state…</div>;
  }
  return (
    <div className="operations-workspace">
      <header className="operations-header">
        <div className="operations-title">
          <h1 className="text-lg font-semibold text-ink">Site operations</h1>
          <p className="text-sm text-dim">
            {payload.site.label} · {payload.site.activity_type ?? "—"}
          </p>
        </div>
        <span className="text-xs text-faint">
          Resolved {formatInstant(payload.resolved_at)}
        </span>
      </header>

      {error ? (
        <div className="operations-error">{String(error)}</div>
      ) : (
        <>
          <div className="operations-scene-row">
            <SiteScene
              selectedObject={null as SceneObjectKey | null}
              onSelectObject={() => {}}
            />
            <WorkflowProgress data={payload} />
          </div>

          <div className="operations-missions">
            <h2 className="text-sm font-semibold text-ink">Missions</h2>
            <ol className="missions-list">
              <MissionItem
                title="Review dust-control measures"
                active
                detail="Inspect the dust-mitigation obligation and its cited source."
              />
              <MissionItem
                title="Review restricted construction activity"
                active
                detail="Check which activity is restricted under the invoked stage."
              />
              <MissionItem
                title="Complete worker communication"
                active
                detail={`${payload.impact.documented - payload.impact.acknowledged} Parchis await worker acknowledgement.`}
              />
              <MissionItem
                title="Inspect evidence provenance"
                active
                detail="Follow a citation back to the official source."
              />
            </ol>
          </div>

          {children}
        </>
      )}
    </div>
  );
}

export function MissionItem({
  title,
  active,
  detail,
}: {
  title: string;
  active?: boolean;
  detail?: string;
}) {
  return (
    <li className={`mission-item ${active ? "mission-item-active" : ""}`}>
      <div className="mission-item-check" aria-hidden="true">
        <span className="site-scene-dot bg-accent" />
      </div>
      <div>
        <div className="text-sm font-medium text-ink">{title}</div>
        {detail && <div className="text-xs text-dim">{detail}</div>}
      </div>
    </li>
  );
}
