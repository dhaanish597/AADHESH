"use client";

import type { SupervisorPayload } from "@/lib/types";
import { formatInstant, stageName } from "@/lib/format";
import { CitationBlock, IconCheck, IconFile, IconUsers, obligationView } from "@/components/ui";
import { SiteScene3D } from "@/components/SiteScene3D";
import type { ReactNode } from "react";

export type SceneObjectKey =
  | "activity-zone"
  | "dust-zone"
  | "restricted-area"
  | "worker-point"
  | "evidence-station"
  | "terminal";

function isRestrictionObligation(item: SupervisorPayload["obligations"][number]) {
  return /restrict/i.test(`${item.obligation_id} ${item.label} ${item.required_action} ${item.reason}`);
}

function findSiteObligation(
  payload: SupervisorPayload,
  matches: (item: SupervisorPayload["obligations"][number]) => boolean,
) {
  return payload.obligations.find((item) => item.applicable === true && matches(item))
    ?? payload.obligations.find((item) => item.applicable === null && matches(item))
    ?? null;
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
        {total > 0 && value >= total ? (
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

export function WorkflowProgress({ data, onOpenWorkers }: WorkflowProgressProps & {
  onOpenWorkers: (filter: "all" | "registered" | "issued" | "pending" | "acknowledged" | "documentation") => void;
}) {
  const registered = data.impact.readiness_total;
  const registrationDocumented = data.impact.readiness_ready;
  const issued = data.impact.documented;
  const acknowledged = data.impact.acknowledged;

  return (
    <div className="workflow-progress" aria-label="Worker workflow progress">
      <div className="workflow-progress-rail">
        {[
          { title: "Workers rostered", value: registered, total: registered, detail: `${registered} people on this site`, filter: "all" as const },
          { title: "Registration documented", value: registrationDocumented, total: registered, detail: `${registered - registrationDocumented} records need review`, filter: "registered" as const },
          { title: "Parchis issued", value: issued, total: registered, detail: `${Math.max(0, registered - issued)} still to issue`, filter: "issued" as const },
          { title: "Worker acknowledgement", value: acknowledged, total: issued, detail: `${Math.max(0, issued - acknowledged)} awaiting worker action`, filter: "pending" as const },
        ].map((node) => (
          <ProgressNode
            key={node.title}
            title={node.title}
            value={node.value}
            total={node.total}
            detail={node.detail}
            selected={false}
            onClick={() => onOpenWorkers(node.filter)}
          />
        ))}
      </div>
      <p className="text-xs text-faint">Registration paperwork and worker acknowledgement are separate records. Neither count establishes financial entitlement.</p>
    </div>
  );
}

interface InspectorProps {
  object: SceneObjectKey | null;
  payload: SupervisorPayload | null;
  onClose: () => void;
  onNavigateView: (view: "site" | "missions" | "workers" | "orders" | "evidence") => void;
}

export function SiteObjectInspector({ object, payload, onClose, onNavigateView }: InspectorProps) {
  if (!object || !payload) return null;

  const openCitation = (
    sourceDoc: string,
    page: number,
    quote: string,
    hash?: string | null,
  ) => (
    <CitationBlock sourceDoc={sourceDoc} page={page} quote={quote} hash={hash} />
  );

  const dustObligation = findSiteObligation(payload, (item) => item.label.toLowerCase().includes("dust"));
  const restrictionObligation = findSiteObligation(payload, isRestrictionObligation);
  const workerObligation = findSiteObligation(payload, (item) => item.issues_parchi);

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
              The site profile identifies {payload.site.activity_type ?? "no activity type"}. The resolver uses this profile and the official invocation to determine applicable obligations. This drawing is not a live site feed.
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
              The status and cited clause below come from the resolver. This inspector does not change whether an activity is permitted.
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
                <button type="button" className="inspector-action" onClick={() => onNavigateView("missions")}>Open mission details</button>
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">
                The resolver returned no applicable dust-control record for this site and scenario.
              </p>
            )}
          </div>
        )}

        {object === "restricted-area" && (
          <div className="site-inspector-card">
            <p className="text-sm font-medium text-ink">Restricted work area</p>
            <p className="mt-2 text-sm text-dim">
              This location is illustrative. Any restriction and cited condition shown here come from the site-level resolver result.
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
                <button type="button" className="inspector-action" onClick={() => onNavigateView("missions")}>Review mission conditions</button>
              </div>
            ) : (
              <p className="mt-4 text-xs text-faint">
                The resolver returned no applicable restriction record for this site and scenario.
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
            <button type="button" className="inspector-action" onClick={() => onNavigateView("workers")}>Open workforce explorer</button>
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
            <button type="button" className="inspector-action" onClick={() => onNavigateView("evidence")}>Open evidence explorer</button>
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
            <button type="button" className="inspector-action" onClick={() => onNavigateView("orders")}>Open Standing Orders</button>
          </div>
        )}
      </div>
    </aside>
  );
}

export function OperationsWorkspace({
  payload,
  error,
  selectedObject,
  onSelectObject,
  onCloseInspector,
  activeWorkspaceView,
  onNavigateView,
  onOpenWorkers,
  children,
}: {
  payload: SupervisorPayload | null;
  error: unknown;
  selectedObject: SceneObjectKey | null;
  onSelectObject: (object: SceneObjectKey) => void;
  onCloseInspector: () => void;
  activeWorkspaceView: "site" | "missions" | "workers" | "orders" | "evidence";
  onNavigateView: (view: "site" | "missions" | "workers" | "orders" | "evidence") => void;
  onOpenWorkers: (filter: "all" | "registered" | "issued" | "pending" | "acknowledged" | "documentation") => void;
  children?: ReactNode;
}) {
  if (!payload) {
    return <div className="operations-loading">Resolving site state…</div>;
  }
  const dustObligation = findSiteObligation(payload, (entry) => /dust/i.test(entry.label));
  const restrictionObligation = findSiteObligation(payload, isRestrictionObligation);
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
            <SiteScene3D
              selectedObject={selectedObject}
              onSelectObject={onSelectObject}
              payload={payload}
            />
            {selectedObject ? (
              <SiteObjectInspector
                object={selectedObject}
                payload={payload}
                onClose={onCloseInspector}
                onNavigateView={onNavigateView}
              />
            ) : (
              <WorkflowProgress data={payload} onOpenWorkers={onOpenWorkers} />
            )}
          </div>

          {(activeWorkspaceView === "site" || activeWorkspaceView === "missions") && <div className="operations-missions">
            <h2 className="text-sm font-semibold text-ink">Missions</h2>
            <ol className="missions-list">
              <MissionItem
                title="Review dust-control measures"
                detail="Inspect the dust-mitigation obligation and its cited source."
                status={dustObligation ? obligationView(dustObligation.status, dustObligation.applicable).label : "Not in scope"}
                onClick={() => onSelectObject("dust-zone")}
              />
              <MissionItem
                title="Review restricted construction activity"
                detail="Check which activity is restricted under the invoked stage."
                status={restrictionObligation ? obligationView(restrictionObligation.status, restrictionObligation.applicable).label : "Check site conditions"}
                onClick={() => onSelectObject("restricted-area")}
              />
              <MissionItem
                title="Complete worker communication"
                detail={`${payload.impact.documented - payload.impact.acknowledged} Parchis await worker acknowledgement.`}
                status={`${payload.impact.acknowledged} of ${payload.impact.documented} acknowledged`}
                onClick={() => onNavigateView("workers")}
              />
              <MissionItem
                title="Inspect evidence provenance"
                detail="Follow a citation back to the official source."
                status={payload.fully_sourced ? "Sources verified" : "Source review needed"}
                onClick={() => onNavigateView("evidence")}
              />
            </ol>
          </div>}

          {children}
        </>
      )}
    </div>
  );
}

export function MissionItem({
  title,
  detail,
  status,
  onClick,
}: {
  title: string;
  detail?: string;
  status: string;
  onClick: () => void;
}) {
  return (
    <li className="mission-item">
      <button type="button" className="mission-item-button" onClick={onClick}>
      <div className="mission-item-check" aria-hidden="true">
        <span className="site-scene-dot bg-faint" />
      </div>
      <div>
        <div className="text-sm font-medium text-ink">{title}</div>
        {detail && <div className="text-xs text-dim">{detail}</div>}
      </div>
      <span className="mission-item-status">{status}</span>
      </button>
    </li>
  );
}
