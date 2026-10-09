"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Button,
  CitationBlock,
  ErrorNote,
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
import { getJson, postJson } from "@/lib/api";
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
            <span className="data text-[12px] text-faint">{obligation.obligation_id}</span>
          </div>
          <h3 className="text-sm font-semibold leading-snug text-ink">{obligation.label}</h3>
          <p className="mt-2 text-sm leading-relaxed text-dim">{obligation.required_action}</p>
          <p className="mt-2 text-xs leading-relaxed text-faint">{obligation.reason}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="label">Clause</div>
          <div className="data text-[12px] text-dim">{obligation.source_doc}</div>
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
        </div>
      )}
    </article>
  );
}

export default function SupervisorPage() {
  const [scenario, setScenario] = useState<Scenario>("replay");
  const [reading, setReading] = useState<ReadingKey>("aligned");
  const [data, setData] = useState<SupervisorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [workers, setWorkers] = useState<QrWorker[] | null>(null);
  const [qrBusy, setQrBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (sc: Scenario, rd: ReadingKey) => {
    setError(null);
    try {
      const payload = await getJson<SupervisorPayload>(
        `/api/supervisor?scenario=${sc}&reading=${rd}`,
      );
      setData(payload);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    setData(null);
    void load(scenario, reading);
  }, [scenario, reading, load]);

  const createOrder = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await postJson<{ standing_order: unknown; impact: SupervisorPayload["impact"] }>(
        "/api/standing-order",
        { scenario },
      );
      await load(scenario, reading);
      await loadQr();
      setNotice("Standing Order signed, activated and worker parchis opened.");
      void res;
    } catch (err) {
      setError((err as Error).message);
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
      setError((err as Error).message);
    } finally {
      setQrBusy(false);
    }
  };

  const acknowledgeAll = async () => {
    if (!workers) return;
    setQrBusy(true);
    setError(null);
    try {
      for (const w of workers) {
        if (!w.payload || (w.state && w.state !== "pending_ack")) continue;
        await postJson("/api/worker/acknowledge", {
          payload: w.payload,
          worker_id: w.worker_id,
        });
      }
      await loadQr();
      await load(scenario, reading);
      setNotice("Remaining workers simulated their own scan + confirm.");
    } catch (err) {
      setError((err as Error).message);
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
              { value: "current", label: "Live corpus" },
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

      {error && (
        <div className="mt-5">
          <ErrorNote>
            {error}
            <span className="block text-xs text-danger/80">
              Is the API running? Start it with <code className="data">make api</code>.
            </span>
          </ErrorNote>
        </div>
      )}

      {!data && !error && <Loading label="Resolving obligations from the verified corpus" />}

      {data && (
        <div className="mt-6 space-y-6">
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
                <Pill tone={data.official_stage === "NONE" ? "neutral" : "warn"}>
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
                    <KeyValue k="Order">{data.stage_detail.order_doc_id ?? "—"}</KeyValue>
                    <KeyValue k="Source hash">
                      <span title={data.official_invocation?.citation?.source_hash ?? undefined}>
                        {shortHash(data.official_invocation?.citation?.source_hash)}
                      </span>
                    </KeyValue>
                    {data.stage_detail.revoked_at && (
                      <KeyValue k="Revoked">
                        {formatInstant(data.stage_detail.revoked_at)} — this stage is not in force
                      </KeyValue>
                    )}
                  </dl>
                </div>
                <div>
                  <dl>
                    <KeyValue k="Nearest station">{data.reading?.station_id ?? "—"}</KeyValue>
                    <KeyValue k="Reading">
                      {data.reading ? `${data.reading.value} ${data.reading.parameter}` : "—"}
                    </KeyValue>
                    <KeyValue k="Timestamp">
                      {formatInstant(data.reading?.observed_at)}
                    </KeyValue>
                    <KeyValue k="Freshness">
                      {freshnessLabel(data.reading?.freshness, data.reading?.age_minutes)}
                    </KeyValue>
                    <KeyValue k="Provenance">
                      <Pill tone={data.reading?.provenance === "measured" ? "ok" : "warn"}>
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
                    Switch the scenario to <span className="data">Stage III replay</span> to see
                    how a real invocation flows through the system.
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
                      Observed AQI implies {stageName(data.implied_stage)}; the verified official
                      invocation is {stageName(data.official_stage)}. Aadesh does not infer legal
                      activation from AQI — obligations are evaluated against the official order.
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
                  className={`h-3.5 w-3.5 transition-transform ${showAll ? "rotate-90" : ""}`}
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
                    {data.obligations.filter((o) => o.applicable !== true).length} further clause
                    {data.obligations.filter((o) => o.applicable !== true).length === 1 ? "" : "s"}{" "}
                    are outside this site&apos;s scope. They are shown, never hidden, because an
                    incomplete picture is itself a compliance risk.
                  </p>
                )}
            </div>
            {!data.fully_sourced && (
              <p className="mt-4 border border-danger/50 bg-danger/10 p-3 text-xs text-danger">
                Not fully sourced: {data.excluded_obligations.length} clause(s) were excluded
                because a citation could not be re-proved. Run <span className="data">make verify</span>.
              </p>
            )}
          </Panel>

          {/* ---------------------------------------------------- standing order */}
          <Panel
            title="Standing Order"
            subtitle="A signed, narrow, time-bounded pre-commitment — not an autonomous permission."
            actions={
              order ? (
                <Pill tone={orderActive ? "ok" : "neutral"}>{order.projected_status}</Pill>
              ) : (
                <Pill tone="neutral">Not created</Pill>
              )
            }
          >
            {order ? (
              <div className="grid gap-3 lg:grid-cols-2">
                <dl>
                  <KeyValue k="Order id">{order.standing_order_id}</KeyValue>
                  <KeyValue k="Trigger">{stageName(order.trigger.stage)} · {order.trigger.match}</KeyValue>
                  <KeyValue k="Actions">
                    {order.actions.map((a) => a.action).join(" + ")}
                  </KeyValue>
                  <KeyValue k="Expires">{formatInstant(order.valid_until)}</KeyValue>
                </dl>
                <dl>
                  <KeyValue k="Signed by">{order.supervisor_id}</KeyValue>
                  <KeyValue k="Signed at">{formatInstant(order.signed_at)}</KeyValue>
                  <KeyValue k="Commitment hash">{shortHash(order.commitment_hash)}</KeyValue>
                  <KeyValue k="Trigger fingerprint">{shortHash(order.trigger_fingerprint ?? null)}</KeyValue>
                </dl>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-4">
                <p className="text-sm text-dim">
                  Pre-commit now so a verified Stage {stageName(3).replace("Stage ", "")} invocation
                  fires the dust-work halt and opens one parchi per rostered worker without waiting
                  on the supervisor.
                </p>
                <Button onClick={createOrder} disabled={busy}>
                  <IconShield className="h-4 w-4" />
                  {busy ? "Signing…" : "Issue / activate Standing Order"}
                </Button>
              </div>
            )}
            {order && (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={loadQr} disabled={qrBusy}>
                  <IconUsers className="h-4 w-4" />
                  {workers ? "Refresh worker QR codes" : "Show worker QR codes"}
                </Button>
                <Link href="/cedar">
                  <Button variant="ghost">
                    Try a forbidden action <IconArrow className="h-4 w-4" />
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

          {/* ---------------------------------------------------- worker impact */}
          <Panel
            title="Worker impact"
            subtitle="Displacement is documented, not priced. The corpus establishes no monetary amount."
          >
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                { k: "Workers affected", v: data.impact.affected },
                { k: "Parchis created", v: data.impact.documented },
                { k: "Acknowledged", v: `${data.impact.acknowledged}/${data.impact.documented || data.impact.affected}` },
                { k: "Claim readiness", v: `${data.impact.readiness_ready}/${data.impact.readiness_total}` },
              ].map((m) => (
                <div key={m.k} className="border border-line bg-panelAlt p-3">
                  <div className="font-mono text-2xl font-semibold text-ink">{m.v}</div>
                  <div className="label mt-1">{m.k}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-faint">
              “Claim readiness” counts workers with a registration number on file — a
              documentation measure. It is not a claim that anyone is entitled to any sum. No
              rupee figure is shown because the verified corpus establishes none; worker count is
              never multiplied into an amount.
            </p>
          </Panel>

          {/* ---------------------------------------------------- QR grid */}
          {workers && (
            <Panel
              title="Worker acknowledgement — QR grid"
              subtitle="Each code carries an opaque token and nothing else. A worker scans, then confirms."
              actions={
                <Button variant="secondary" onClick={acknowledgeAll} disabled={qrBusy}>
                  {qrBusy ? "Working…" : "Simulate remaining scans"}
                </Button>
              }
            >
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                {workers.map((w) => {
                  const acked = w.state === "acknowledged" || w.state === "sealed";
                  return (
                    <div
                      key={w.worker_id}
                      className={`border p-2 text-center ${
                        acked ? "border-success/50 bg-success/5" : "border-line bg-panelAlt"
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between px-1">
                        <span className="data text-[11px] text-dim">{w.worker_id}</span>
                        {acked ? (
                          <IconCheck className="h-3.5 w-3.5 text-success" />
                        ) : (
                          <span className="label">{w.registered ? "reg" : "—"}</span>
                        )}
                      </div>
                      {w.payload ? (
                        <Link
                          href={`/worker?payload=${encodeURIComponent(w.payload)}`}
                          className="block"
                          title="Open this worker's parchi screen as if scanned"
                        >
                          <div className="mx-auto w-fit">
                            <Qr value={w.payload} alt={`Acknowledgement QR for ${w.worker_id}`} />
                          </div>
                        </Link>
                      ) : (
                        <div className="grid h-[148px] place-items-center border border-line text-xs text-faint">
                          link issued
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}

          <details className="border border-line bg-panel p-4">
            <summary className="cursor-pointer text-sm text-dim">
              <IconTerminal className="mr-2 inline h-4 w-4" />
              Resolver audit — reason strings and the resolution summary
            </summary>
            <pre className="data mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-[12px] text-dim">
              {JSON.stringify(
                { summary: data.summary, stage_reason: data.stage_reason, mode: data.mode, resolved_at: data.resolved_at },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
