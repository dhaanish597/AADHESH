"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Button,
  CitationBlock,
  ApiErrorNote,
  IconAlert,
  IconArrow,
  IconCheck,
  IconChevron,
  IconFile,
  IconShield,
  IconTerminal,
  IconUsers,
  KeyValue,
  Loading,
  Panel,
  Pill,
  obligationView,
} from "@/components/ui";
import { Qr } from "@/components/Qr";
import {
  OperationsWorkspace,
  SiteObjectInspector,
  type SceneObjectKey,
} from "@/components/OperationsWorkspace";
import { SceneObjectToggle } from "./SceneObjectToggle";
import { getJson, postJson, failureOf, type ApiFailure } from "@/lib/api";
import { formatInstant, freshnessLabel, shortHash, stageName } from "@/lib/format";
import type { Obligation, SupervisorPayload } from "@/lib/types";

type Scenario = "replay" | "current";
type ReadingKey = "aligned" | "divergent" | "none";

type QrWorker = {
  worker_id: string;
  display_name: string;
  registered: boolean;
  parchi_id: string | null;
  payload: string | null;
  state: string | null;
};

function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="label">{label}</span>
      <div className="inline-flex border border-line" role="group" aria-label={label}>
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={value === opt.value}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
              value === opt.value
                ? "bg-accent text-black"
                : "bg-panelAlt text-dim hover:text-ink"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ObligationCard({ obligation }: { obligation: Obligation }) {
  const [open, setOpen] = useState(false);
  const view = obligationView(obligation.status, obligation.applicable);
  const evidence = (obligation.evidence ?? []).filter(Boolean);

  return (
    <article className="border border-line bg-panelAlt">
      <div className="flex items-start justify-between gap-4 p-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Pill tone={view.tone}>{view.label}</Pill>
            {obligation.issues_parchi && <Pill tone="info">Parchi</Pill>}
          </div>
          <h3 className="text-sm font-semibold leading-snug text-ink">{obligation.label}</h3>
          <p className="mt-2 text-sm leading-relaxed text-dim">{obligation.required_action}</p>
          <p className="mt-2 text-xs leading-relaxed text-faint">{obligation.reason}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="label">Official source</div>
          <div className="data text-[12px] text-faint">page {obligation.source_page}</div>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent transition-colors hover:text-amber-300"
          >
            <IconFile className="h-3.5 w-3.5" />
            {open ? "Hide source" : "View source"}
          </button>
        </div>
      </div>
      {open && (
        <div className="space-y-2 border-t border-line p-4">
          <CitationBlock
            sourceDoc={obligation.source_doc}
            page={obligation.source_page}
            quote={obligation.source_quote}
            hash={obligation.source_hash}
          />
          {evidence.length > 1 && (
            <details className="border border-line bg-panel p-3">
              <summary className="cursor-pointer text-xs text-dim">
                Supporting evidence ({evidence.length - 1} further citation
                {evidence.length - 1 === 1 ? "" : "s"})
              </summary>
              <div className="mt-3 space-y-2">
                {evidence
                  .filter((e) => e!.source_quote !== obligation.source_quote)
                  .map((e, i) => (
                    <CitationBlock
                      key={`${e!.source_doc}-${e!.source_page}-${i}`}
                      sourceDoc={e!.source_doc}
                      page={e!.source_page}
                      quote={e!.source_quote}
                      hash={e!.source_hash}
                    />
                  ))}
              </div>
            </details>
          )}
          <details className="border-t border-line pt-3">
            <summary className="cursor-pointer text-xs text-faint">Technical citation details</summary>
            <dl className="mt-2">
              <KeyValue k="Rule reference">{obligation.obligation_id}</KeyValue>
              <KeyValue k="Source document">{obligation.source_doc}</KeyValue>
              <KeyValue k="SHA-256">{shortHash(obligation.source_hash)}</KeyValue>
            </dl>
          </details>
        </div>
      )}
    </article>
  );
}

export default function SupervisorPage() {
  const [scenario, setScenario] = useState<Scenario>("current");
  const [reading, setReading] = useState<ReadingKey>("aligned");
  const [data, setData] = useState<SupervisorPayload | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [workers, setWorkers] = useState<QrWorker[] | null>(null);
  const [qrBusy, setQrBusy] = useState(false);
  const [workerQuery, setWorkerQuery] = useState("");
  const [workerFilter, setWorkerFilter] = useState<
    "all" | "pending" | "acknowledged" | "documentation" | "issued"
  >("all");
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<SceneObjectKey | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const load = useCallback(async (sc: Scenario, rd: ReadingKey) => {
    setError(null);
    try {
      const payload = await getJson<SupervisorPayload>(
        `/api/supervisor?scenario=${sc}&reading=${rd}`,
      );
      setData(payload);
    } catch (err) {
      setError(failureOf(err));
    }
  }, []);

  useEffect(() => {
    setData(null);
    void load(scenario, reading);
  }, [scenario, reading, load]);

  const createOrder = async () => {
    if (!replayCanRun) {
      setNotice(
        "Preview only: no active official Stage III invocation is available in the current corpus.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await postJson<{
        standing_order: unknown;
        impact: SupervisorPayload["impact"];
      }>("/api/standing-order", { scenario });
      await load(scenario, reading);
      await loadQr();
      setNotice(
        "Historical replay ran locally: the Standing Order was authorized, and demo Parchis were opened.",
      );
      void res;
    } catch (err) {
      setError(failureOf(err));
    } finally {
      setBusy(false);
    }
  };

  const loadQr = async () => {
    setQrBusy(true);
    try {
      const res = await postJson<{ workers: QrWorker[] }>("/api/roster/qr", { scenario });
      setWorkers(res.workers);
    } catch (err) {
      setError(failureOf(err));
    } finally {
      setQrBusy(false);
    }
  };

  const obligations = useMemo(() => {
    if (!data) return [];
    const applicable = data.obligations.filter((o) => o.applicable === true);
    const rest = data.obligations.filter((o) => o.applicable !== true);
    return showAll ? [...applicable, ...rest] : applicable;
  }, [data, showAll]);

  const order = data?.standing_order;
  const orderActive = order && order.projected_status === "active";
  const replayCanRun = data?.mode === "REPLAY" && data.official_stage !== "NONE";
  const selectedWorker = workers?.find(
    (worker) => worker.worker_id === selectedWorkerId,
  ) ?? null;
  const visibleWorkers = workers?.filter((worker) => {
    const query = workerQuery.trim().toLocaleLowerCase();
    const matchesQuery =
      !query ||
      worker.display_name.toLocaleLowerCase().includes(query) ||
      worker.worker_id.toLocaleLowerCase().includes(query);
    const acknowledged =
      worker.state === "acknowledged" || worker.state === "sealed";
    const matchesFilter =
      workerFilter === "all"
        || (workerFilter === "pending" && !acknowledged)
        || (workerFilter === "acknowledged" && acknowledged)
        || (workerFilter === "documentation" && !worker.registered)
        || (workerFilter === "issued" && Boolean(worker.parchi_id));
    return matchesQuery && matchesFilter;
  }) ?? [];

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <div className="label">Supervisor console</div>
          <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight">
            {data?.site.label ?? "Construction Site — Delhi-NCR"}
          </h1>
          <p className="mt-1 text-sm text-dim">
            {data?.site.activity_type ?? "—"} · {data?.site.project_category ?? "—"}
          </p>
        </div>
        <div className="flex flex-wrap gap-4">
          <Segmented
            label="Scenario"
            value={scenario}
            onChange={(v) => setScenario(v)}
            options={[
              { value: "replay", label: "Stage III replay" },
              { value: "current", label: "Current corpus" },
            ]}
          />
          <Segmented
            label="Station reading"
            value={reading}
            onChange={(v) => setReading(v)}
            options={[
              { value: "aligned", label: "Aligned" },
              { value: "divergent", label: "Divergent" },
              { value: "none", label: "None" },
            ]}
          />
        </div>
      </header>

      {error && <div className="mt-5"><ApiErrorNote error={error} /></div>}

      {!data && !error && (
        <Loading label="Resolving obligations from the verified corpus" />
      )}

      {data && (
        <div className="mt-6 space-y-6">
          {/* ---------------------------------------------------- operations workspace */}
          <OperationsWorkspace payload={data} error={error} busy={busy}>
            {/* ---------------------------------------------------- stage status */}
            <Panel
              title="Stage status"
              subtitle="The stage is invoked by a CAQM order, not computed from a reading."
              actions={
                data.stage_detail.is_replay ? (
                  <Pill tone="warn">
                    <IconAlert className="h-3.5 w-3.5" /> Historical replay
                  </Pill>
                ) : (
                  <Pill
                    tone={data.official_stage === "NONE" ? "neutral" : "warn"}
                  >
                    {data.official_stage === "NONE" ? "No invocation" : "Official"}
                  </Pill>
                )
              }
            >
              {data.official_stage !== "NONE" ? (
                <div className="grid gap-6 lg:grid-cols-2">
                  <div>
                    <div className="font-mono text-3xl font-semibold tracking-tight text-accent">
                      {stageName(data.official_stage)}
                    </div>
                    <p className="mt-1 text-sm text-dim">
                      Officially invoked by CAQM
                      {data.stage_detail.order_date
                        ? ` · order dated ${formatInstant(data.stage_detail.order_date)}`
                        : ""}
                    </p>
                    <dl className="mt-4">
                      <KeyValue k="Order">
                        {data.stage_detail.order_doc_id ?? "—"}
                      </KeyValue>
                      <KeyValue k="Source hash">
                        <span
                          title={
                            data.official_invocation?.citation?.source_hash ??
                            undefined
                          }
                        >
                          {shortHash(
                            data.official_invocation?.citation?.source_hash,
                          )}
                        </span>
                      </KeyValue>
                      {data.stage_detail.revoked_at && (
                        <KeyValue k="Revoked">
                          {formatInstant(data.stage_detail.revoked_at)} — this
                          stage is not in force
                        </KeyValue>
                      )}
                    </dl>
                  </div>
                  <div>
                    <dl>
                      <KeyValue k="Nearest station">
                        {data.reading?.station_id ?? "—"}
                      </KeyValue>
                      <KeyValue k="Reading">
                        {data.reading
                          ? `${data.reading.value} ${data.reading.parameter}`
                          : "—"}
                      </KeyValue>
                      <KeyValue k="Timestamp">
                        {formatInstant(data.reading?.observed_at)}
                      </KeyValue>
                      <KeyValue k="Freshness">
                        {freshnessLabel(
                          data.reading?.freshness,
                          data.reading?.age_minutes,
                        )}
                      </KeyValue>
                      <KeyValue k="Provenance">
                        <Pill
                          tone={
                            data.reading?.provenance === "measured"
                              ? "ok"
                              : "warn"
                          }
                        >
                          {data.reading?.provenance ?? "none"}
                        </Pill>
                      </KeyValue>
                    </dl>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-3">
                  <IconAlert className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
                  <div>
                    <p className="text-sm font-medium text-ink">
                      No verified current CAQM invocation is present.
                    </p>
                    <p className="mt-1 text-sm text-dim">{data.stage_reason}</p>
                    <p className="mt-2 text-xs text-faint">
                      Switch the scenario to{" "}
                      <span className="data">Stage III replay</span> to see how a
                      real invocation flows through the system.
                    </p>
                  </div>
                </div>
              )}

              {data.stage_detail.discrepancy && (
                <div className="mt-5 border border-accent/50 bg-accent/10 p-3" role="status">
                  <div className="flex items-start gap-2">
                    <IconAlert className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                    <div>
                      <p className="data text-xs font-semibold uppercase tracking-[0.12em] text-accent">
                        Implied stage differs from official stage
                      </p>
                      <p className="mt-1 text-sm text-ink/90">{data.stage_reason}</p>
                      <p className="mt-1 text-xs text-dim">
                        Observed AQI implies {stageName(data.implied_stage)}; the
                        verified official invocation is{" "}
                        {stageName(data.official_stage)}. Aadesh does not infer
                        legal activation from AQI — obligations are evaluated against
                        the official order.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {data.stage_detail.is_replay && data.replay_notice && (
                <p className="mt-4 border-l-2 border-accent/50 pl-3 text-xs leading-relaxed text-faint">
                  {data.replay_notice}
                </p>
              )}
            </Panel>

            {/* ---------------------------------------------------- obligations */}
            <Panel
              title="Your obligations"
              subtitle={
                data.official_stage === "NONE"
                  ? "No stage-triggered clause is activated without an official invocation."
                  : `${data.summary.applicable} applicable clause surface for this site and activity.`
              }
              actions={
                <button
                  type="button"
                  onClick={() => setShowAll((v) => !v)}
                  aria-pressed={showAll}
                  className="inline-flex items-center gap-1 text-xs font-medium text-dim transition-colors hover:text-ink"
                >
                  {showAll ? "Show applicable only" : "Show all clauses"}
                  <IconChevron
                    className={`h-3.5 w-3.5 transition-transform ${
                      showAll ? "rotate-90" : ""
                    }`}
                  />
                </button>
              }
            >
              <div className="space-y-3">
                {obligations.map((o) => (
                  <ObligationCard key={o.obligation_id} obligation={o} />
                ))}
                {!showAll &&
                  data.obligations.some((o) => o.applicable !== true) && (
                    <p className="text-xs text-faint">
                      {data.obligations.filter((o) => o.applicable !== true).length}{" "}
                      further clause
                      {data.obligations.filter((o) => o.applicable !== true).length ===
                      1
                        ? ""
                        : "s"}{" "}
                      are outside this site&apos;s scope. They are shown, never hidden,
                      because an incomplete picture is itself a compliance risk.
                    </p>
                  )}
              </div>
              {!data.fully_sourced && (
                <p className="mt-4 border border-danger/50 bg-danger/10 p-3 text-xs text-danger">
                  Not fully sourced:{" "}
                  {data.excluded_obligations.length} clause(s) were excluded because a
                  citation could not be re-proved. Run{" "}
                  <span className="data">make verify</span>.
                </p>
              )}
            </Panel>

            {/* ---------------------------------------------------- standing order */}
            <Panel
              title="Standing Order"
              subtitle="One site · exact Stage III trigger · explicit halt and Parchi actions · seven-day validity. No arbitrary code or agent instructions."
              actions={
                order ? (
                  <Pill
                    tone={orderActive ? "ok" : "neutral"}
                  >
                    {orderActive
                      ? "PRE-COMMITMENT ARMED"
                      : order.projected_status}
                  </Pill>
                ) : (
                  <Pill tone="neutral">Not created</Pill>
                )
              }
            >
              {order ? (
                <>
                  <div className="grid gap-3 lg:grid-cols-2">
                    <dl>
                      <KeyValue k="Trigger">
                        {stageName(order.trigger.stage)} · {order.trigger.match}
                      </KeyValue>
                      <KeyValue k="Actions">
                        {order.actions.map((a) => a.action).join(" + ")}
                      </KeyValue>
                      <KeyValue k="Valid from">
                        {formatInstant(order.valid_from)}
                      </KeyValue>
                      <KeyValue k="Expires">
                        {formatInstant(order.valid_until)}
                      </KeyValue>
                    </dl>
                  </div>
                  <details className="mt-3 border-t border-line pt-3">
                    <summary className="cursor-pointer text-xs text-faint">
                      Technical commitment details
                    </summary>
                    <dl className="mt-2">
                      <KeyValue k="Order reference">
                        {order.standing_order_id}
                      </KeyValue>
                      <KeyValue k="Site reference">{order.site_id}</KeyValue>
                      <KeyValue k="Supervisor reference">
                        {order.supervisor_id}
                      </KeyValue>
                      <KeyValue k="Signed at">
                        {formatInstant(order.signed_at)}
                      </KeyValue>
                      <KeyValue k="Commitment hash">
                        {shortHash(order.commitment_hash)}
                      </KeyValue>
                      <KeyValue k="Trigger fingerprint">
                        {shortHash(order.trigger_fingerprint ?? null)}
                      </KeyValue>
                    </dl>
                  </details>
                  <div className="mt-5 border-t border-line pt-4">
                    <h3 className="label">
                      Standing Order lifecycle · {order.projected_status}
                    </h3>
                    <ol className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {[
                        ["draft", "Draft", "Written, not yet signed"],
                        ["confirmed", "Signed", "Commitment fixed by supervisor"],
                        [
                          "active",
                          "Pre-commitment",
                          "Eligible for its exact official trigger",
                        ],
                        [
                          "triggered",
                          "Triggered",
                          "Official invocation matched",
                        ],
                        [
                          "completed",
                          "Completed",
                          "Workflow reached its audit step",
                        ],
                        ["expired", "Expired", "Validity window ended"],
                      ].map(([state, title, detail]) => {
                        const current =
                          order.projected_status.toLowerCase() === state;
                        return (
                          <li
                            key={state}
                            aria-current={current ? "step" : undefined}
                            className={`border p-3 ${
                              current
                                ? "border-accent bg-accent/10"
                                : "border-line bg-panelAlt"
                            }`}
                          >
                            <span className="flex items-center gap-2">
                              <span
                                className={`grid h-5 w-5 place-items-center rounded-full border text-[10px] ${
                                  current
                                    ? "border-accent text-accent"
                                    : "border-lineStrong text-faint"
                                }`}
                              >
                                {current ? "•" : ""}
                              </span>
                              <strong
                                className={`text-sm ${
                                  current ? "text-accent" : "text-ink"
                                }`}
                              >
                                {title}
                              </strong>
                            </span>
                            <span className="mt-2 block pl-7 text-xs leading-relaxed text-dim">
                              {detail}
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                    <p className="mt-3 text-xs text-faint">
                      Expiry is computed from the validity window. It can close an
                      order from any non-terminal phase; no revocation transition is
                      offered by the current backend.
                    </p>
                  </div>
                </>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <p className="text-sm text-dim">
                    {replayCanRun
                      ? "Local in-memory demonstration only. The bundled Stage III record is historical and revoked; running this replay shows the authorization and Parchi flow without creating a current restriction."
                      : "Preview only. The current corpus has no active Stage III invocation, so this local action stays disabled."}
                  </p>
                  <Button onClick={createOrder} disabled={busy || !replayCanRun}>
                    <IconShield className="h-4 w-4" />
                    {busy
                      ? "Signing…"
                      : replayCanRun
                        ? "Run Stage III replay demo"
                        : "Preview only"}
                  </Button>
                </div>
              )}
              {order && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={loadQr}
                    disabled={qrBusy}
                  >
                    <IconUsers className="h-4 w-4" />
                    {workers ? "Refresh worker QR codes" : "Show worker QR codes"}
                  </Button>
                  <Link href="/cedar">
                    <Button variant="ghost">
                      Try a forbidden action{" "}
                      <IconArrow className="h-4 w-4" />
                    </Button>
                  </Link>
                </div>
              )}
              {notice && (
                <p className="mt-3 flex items-center gap-2 text-xs text-success">
                  <IconCheck className="h-3.5 w-3.5" /> {notice}
                </p>
              )}
            </Panel>

            {/* ---------------------------------------------------- searchable roster */}
            {workers && (
              <div id="worker-roster" className="scroll-mt-24">
                <Panel
                  title="Worker roster"
                  subtitle="Find a worker, review their documentation and acknowledgement state, then show that worker their one-time QR. A supervisor cannot acknowledge on a worker’s behalf."
                >
                  <div className="flex flex-wrap gap-2" role="group" aria-label="Filter workers">
                    {([
                      ["all", `All workers · ${workers.length}`],
                      [
                        "pending",
                        `Awaiting acknowledgement · ${workers.filter(
                          (w) =>
                            w.state !== "acknowledged" &&
                            w.state !== "sealed",
                        ).length}`,
                      ],
                      [
                        "acknowledged",
                        `Acknowledged · ${workers.filter(
                          (w) =>
                            w.state === "acknowledged" ||
                            w.state === "sealed",
                        ).length}`,
                      ],
                      [
                        "documentation",
                        `Documentation missing · ${workers.filter(
                          (w) => !w.registered,
                        ).length}`,
                      ],
                      [
                        "issued",
                        `Parchis issued · ${workers.filter(
                          (w) => Boolean(w.parchi_id),
                        ).length}`,
                      ],
                    ] as const).map(([filter, label]) => (
                      <button
                        key={filter}
                        type="button"
                        aria-pressed={workerFilter === filter}
                        onClick={() => setWorkerFilter(filter)}
                        className={`border px-3 py-2 text-xs transition-colors ${
                          workerFilter === filter
                            ? "border-accent bg-accent/10 text-accent"
                            : "border-line text-dim hover:text-ink"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="mt-4 block">
                    <span className="sr-only">Search workers by name or reference</span>
                    <input
                      value={workerQuery}
                      onChange={(event) => setWorkerQuery(event.target.value)}
                      placeholder="Search the roster"
                      className="w-full border border-line bg-panelAlt px-3 py-2.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
                    />
                  </label>
                  <div className="mt-3 divide-y divide-line border-y border-line">
                    {visibleWorkers.map((worker) => {
                      const acked =
                        worker.state === "acknowledged" ||
                        worker.state === "sealed";
                      const selected =
                        worker.worker_id === selectedWorkerId;
                      return (
                        <div
                          key={worker.worker_id}
                          className={`flex flex-wrap items-center justify-between gap-3 py-3 ${
                            selected ? "bg-accent/5" : ""
                          }`}
                        >
                          <div className="min-w-0">
                            <div className="font-medium text-ink">
                              {worker.display_name}
                            </div>
                            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-dim">
                              <span>
                                {acked
                                  ? "Parchi acknowledged"
                                  : worker.payload
                                    ? "Awaiting acknowledgement"
                                    : "No Parchi link"}
                              </span>
                              <span>
                                {worker.registered
                                  ? "Registration documented"
                                  : "Registration details missing"}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {worker.payload ? (
                              <Button
                                variant={selected ? "secondary" : "ghost"}
                                onClick={() =>
                                  setSelectedWorkerId(
                                    selected ? null : worker.worker_id,
                                  )
                                }
                              >
                                {selected ? "Close QR" : "Show worker QR"}
                              </Button>
                            ) : (
                              <span className="text-xs text-faint">
                                QR unavailable
                              </span>
                            )}
                            <details className="text-xs text-faint">
                              <summary className="cursor-pointer">Details</summary>
                              <span className="data mt-2 block">
                                {worker.worker_id} ·{" "}
                                {worker.parchi_id ??
                                  "No Parchi reference"}
                              </span>
                            </details>
                          </div>
                        </div>
                      );
                    })}
                    {visibleWorkers.length === 0 && (
                      <p className="py-8 text-center text-sm text-dim">
                        No workers match this search.
                      </p>
                    )}
                  </div>
                  {selectedWorker?.payload && (
                    <div className="mt-5 flex flex-col items-center gap-3 border border-line bg-panelAlt p-5 text-center" aria-live="polite">
                      <h3 className="font-semibold text-ink">
                        Show this one-time code to {selectedWorker.display_name}
                      </h3>
                      <p className="max-w-md text-xs leading-relaxed text-dim">
                        The worker opens their own Parchi and confirms it
                        themselves. This QR contains an opaque token; its value is not
                        displayed here.
                      </p>
                      <Qr
                        value={
                          typeof window === "undefined"
                            ? ""
                            : `${window.location.origin}/worker#payload=${encodeURIComponent(
                                selectedWorker.payload,
                              )}`
                        }
                        alt={`One-time Parchi link for ${selectedWorker.display_name}`}
                      />
                    </div>
                  )}
                  <p className="mt-3 text-xs text-faint">
                    This is the local demonstration roster. Registration
                    documentation does not establish financial entitlement.
                  </p>
                </Panel>
              </div>
            )}

            {workers && workers.length === 0 && (
              <p className="text-sm text-dim">
                No worker records are available in this scenario.
              </p>
            )}

            <details className="border border-line bg-panel p-4">
              <summary className="cursor-pointer text-sm text-dim">
                <IconTerminal className="mr-2 inline h-4 w-4" />
                Resolver audit — reason strings and the resolution summary
              </summary>
              <pre className="data mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-[12px] text-dim">
                {JSON.stringify(
                  {
                    summary: data.summary,
                    stage_reason: data.stage_reason,
                    mode: data.mode,
                    resolved_at: data.resolved_at,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>

            <SceneObjectToggle
              objects={[
                { key: "activity-zone", label: "Activity zone" },
                { key: "dust-zone", label: "Dust zone" },
                { key: "restricted-area", label: "Restricted area" },
                { key: "worker-point", label: "Worker point" },
                { key: "evidence-station", label: "Evidence station" },
                { key: "terminal", label: "Terminal" },
              ]}
              selectedObject={selectedObject}
              setSelectedObject={setSelectedObject}
            />
            {selectedObject && inspectorOpen && (
              <SiteObjectInspector
                object={selectedObject}
                payload={data}
                onClose={() => {
                  setSelectedObject(null);
                  setInspectorOpen(false);
                }}
              />
            )}
          </OperationsWorkspace>
        </div>
      )}
    </div>
  );
}
