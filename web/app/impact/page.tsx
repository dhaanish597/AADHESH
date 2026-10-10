"use client";

import { useCallback, useEffect, useState } from "react";
import { getJson, failureOf, type ApiFailure } from "@/lib/api";
import { formatInstant, formatDate, stageName } from "@/lib/format";
import type { PublicImpactPayload } from "@/lib/types";
import {
  Panel,
  Pill,
  Button,
  IconAlert,
  IconCheck,
  IconArrow,
  Loading,
  ApiErrorNote,
} from "@/components/ui";

type MetricStatus = PublicImpactPayload["metrics"]["sites_with_active_standing_orders"]["status"];

const STATUS_TONE: Record<MetricStatus, "ok" | "neutral" | "warn" | "danger" | "info"> = {
  live: "ok",
  demo: "info",
  synthetic: "warn",
  historical: "warn",
  unavailable: "neutral",
};

const STATUS_LABEL: Record<MetricStatus, string> = {
  live: "LIVE",
  demo: "DEMO DATA",
  synthetic: "SYNTHETIC",
  historical: "HISTORICAL REPLAY",
  unavailable: "NOT YET MEASURED",
};

function MetricCard({
  metric,
}: {
  metric: PublicImpactPayload["metrics"]["sites_with_active_standing_orders"];
}) {
  const status = metric.status;
  const count = metric.count;

  return (
    <article className="border border-line bg-panelAlt p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="label">{metric.label}</span>
        <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Pill>
      </div>

      <div
        className={`font-mono text-4xl font-semibold tracking-tight ${count ? "text-ink" : "text-faint"}`}
        aria-label={`${metric.label}: ${count}`}
      >
        {count ?? "—"}
      </div>

      <p className="mt-3 text-sm leading-relaxed text-dim">{metric.description}</p>

      {metric.reporting_period && (
        <p className="mt-3 text-xs text-faint">
          Reporting period: {formatDate(metric.reporting_period)}
        </p>
      )}

      <p className="mt-3 text-xs leading-relaxed">
        <span className="text-accent">Status:</span> {metric.status_reason}
      </p>
    </article>
  );
}

function DataStatusBanner({
  payload,
}: {
  payload: PublicImpactPayload;
}) {
  const parts: Array<{ tone: "warn" | "danger" | "info"; text: string }> = [];

  if (payload.is_replay) {
    parts.push({
      tone: "warn",
      text: `Historical replay: the Stage III invocation shown here (16 January 2026) was revoked on 22 January 2026. It is not a current official restriction.`,
    });
  }

  if (payload.reading?.is_synthetic) {
    parts.push({
      tone: "warn",
      text: `The air quality reading shown is SYNTHETIC — a demonstration placeholder, not a measured station value.`,
    });
  }

  if (payload.is_current_invocation === false && payload.invocation?.lifecycle === "revoked") {
    parts.push({
      tone: "danger",
      text: `Aadesh does not present revoked orders as live stages. This screen says so explicitly.`,
    });
  }

  if (parts.length === 0) {
    parts.push({
      tone: "info",
      text: `This view reflects the Aadesh demonstration application, not verified Delhi-NCR production data.`,
    });
  }

  return (
    <div className="space-y-3">
      {parts.map((part, i) => (
        <div
          key={i}
          className="border-l-2 border-current/50 pl-3 text-sm leading-relaxed"
          style={{
            color: part.tone === "danger" ? "#f87171" : part.tone === "warn" ? "#fbbf24" : "#60a5fa",
          }}
        >
          {part.text}
        </div>
      ))}
    </div>
  );
}

export default function ImpactPage() {
  const [data, setData] = useState<PublicImpactPayload | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await getJson<PublicImpactPayload>("/api/impact"));
    } catch (err) {
      setError(failureOf(err));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold tracking-tight">Aadesh</h1>
          <Pill tone="neutral">Public environmental impact</Pill>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-dim">
          This page communicates how Aadesh documents the execution of environmental
          restrictions under the Graded Response Action Plan (GRAP) for Delhi-NCR
          construction sites — and the people affected by those actions.
        </p>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-dim">
          It shows aggregate operational information only: sites under Standing Orders,
          sites acknowledging regulated halts, dust-generating activities restricted, and
          workers with documented displacement. It does not show AQI trends, predicted
          pollution, or individual worker records.
        </p>
      </header>

      {error && (
        <div className="mt-5">
          <ApiErrorNote error={error} />
        </div>
      )}

      {!data && !error && <Loading label="Loading public impact data" />}

      {data && (
        <div className="mt-6 space-y-6">
          {/* data status banner */}
          <Panel
            title="Data status"
            subtitle="What this view reflects — and what it does not"
          >
            <DataStatusBanner payload={data} />
          </Panel>

          {/* headline metrics */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              metric={data.metrics.sites_with_active_standing_orders}
            />
            <MetricCard
              metric={data.metrics.sites_acknowledging_regulated_halts}
            />
            <MetricCard metric={data.metrics.dust_activities_halted} />
            <MetricCard
              metric={data.metrics.workers_with_documented_displacement}
            />
          </div>

          {/* invocation detail */}
          {data.invocation && (
            <Panel
              title="Current invocation"
              subtitle="The stage is invoked by a CAQM order, not computed from a reading."
              actions={
                data.is_current_invocation ? (
                  <Pill tone="ok">Current invocation</Pill>
                ) : (
                  <Pill tone="warn">
                    <IconAlert className="h-3.5 w-3.5" /> Not current
                  </Pill>
                )
              }
            >
              <div className="grid gap-4 lg:grid-cols-2">
                <dl>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Stage</dt>
                    <dd className="data text-sm text-ink">
                      {stageName(data.invocation.stage)}
                      {data.invocation.is_current ? (
                        <Pill tone="ok" className="ml-2">in force</Pill>
                      ) : (
                        <Pill tone="warn" className="ml-2">
                          {data.invocation.lifecycle === "revoked"
                            ? "revoked"
                            : "not current"}
                        </Pill>
                      )}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Invoked</dt>
                    <dd className="data text-sm text-ink">
                      {formatInstant(data.invocation.invoked_at)}
                    </dd>
                  </div>
                  {data.invocation.revoked_at && (
                    <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                      <dt className="label pt-0.5">Revoked</dt>
                      <dd className="data text-sm text-ink">
                        {formatInstant(data.invocation.revoked_at)}
                      </dd>
                    </div>
                  )}
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Order</dt>
                    <dd className="data text-sm text-ink">
                      {data.invocation.order_doc_id}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 py-2">
                    <dt className="label pt-0.5">Source hash</dt>
                    <dd className="data text-sm text-ink">
                      {data.invocation.order_sha256.slice(0, 16)}…
                    </dd>
                  </div>
                </dl>
                <p className="text-sm leading-relaxed text-dim lg:col-span-2">
                  {data.invocation.describe}
                </p>
              </div>
            </Panel>
          )}

          {/* reading detail */}
          {data.reading && (
            <Panel
              title="Air quality reading"
              subtitle="A reading may imply a stage, but it does not invoke one."
              actions={
                data.reading.is_synthetic ? (
                  <Pill tone="warn">SYNTHETIC</Pill>
                ) : data.reading.is_measured ? (
                  <Pill tone="ok">MEASURED</Pill>
                ) : (
                  <Pill tone="neutral">{data.reading.provenance}</Pill>
                )
              }
            >
              <div className="grid gap-3 lg:grid-cols-2">
                <dl>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Station</dt>
                    <dd className="data text-sm text-ink">{data.reading.station_id}</dd>
                  </div>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Reading</dt>
                    <dd className="data text-sm text-ink">
                      {data.reading.value} {data.reading.parameter}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2">
                    <dt className="label pt-0.5">Observed</dt>
                    <dd className="data text-sm text-ink">
                      {formatInstant(data.reading.observed_at)}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 py-2">
                    <dt className="label pt-0.5">Provenance</dt>
                    <dd className="data text-sm text-ink uppercase tracking-wide">
                      {data.reading.provenance}
                    </dd>
                  </div>
                </dl>
                <p className="text-sm leading-relaxed text-dim lg:col-span-2">
                  Even when a station reading implies a GRAP stage, Aadesh evaluates
                  obligations against the verified official invocation, not against the
                  reading alone. A high AQI does not, by itself, mean a halt is in force.
                </p>
              </div>
            </Panel>
          )}

          {/* how Aadesh works */}
          <Panel
            title="How Aadesh documents compliance"
            subtitle="From official source to documented operational action"
          >
            <ol className="space-y-4 text-sm">
              {[
                {
                  n: "1",
                  title: "Official CAQM source",
                  body: "Aadesh ingests CAQM GRAP orders and the revised GRAP schedule. Each document is hashed; every quoted clause is re-checked verbatim against the hashed bytes by `make verify`.",
                },
                {
                  n: "2",
                  title: "Deterministic site-specific obligation resolution",
                  body: "The verified corpus is resolved against a site profile. Applicability and compliance are computed from the cited rules, not from a model or a heuristic. The stage comes from the official invocation, not from arithmetic on a reading.",
                },
                {
                  n: "3",
                  title: "Documented operational action",
                  body: "Where an obligation applies and issues a Parchi, Aadesh records the operational action — for example, restricting a listed dust-generating activity. A Standing Order is a signed, time-bounded pre-commitment to act if a stage is invoked; it is not an autonomous permission and not itself proof a halt occurred.",
                },
                {
                  n: "4",
                  title: "Worker acknowledgement and evidence",
                  body: "A Parchi (पर्ची) is issued to each rostered worker. The worker acknowledges it themselves; the record is then sealed over a content hash. The acknowledgement is evidence that the worker was informed, not a payment or an entitlement determination.",
                },
              ].map((item) => (
                <li key={item.n} className="flex gap-4">
                  <span className="shrink-0 border border-accent/50 bg-accent/10 font-mono text-xs text-accent">
                    {item.n}
                  </span>
                  <div>
                    <h3 className="font-semibold text-ink">{item.title}</h3>
                    <p className="mt-1 text-dim">{item.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>

          {/* what these numbers mean */}
          <Panel
            title="What these numbers mean"
            subtitle="Documented operational activity is not the same as measured environmental outcome"
          >
            <div className="space-y-3 text-sm leading-relaxed text-dim">
              <p>
                The metrics on this page count <span className="text-ink">documented
                operational activity</span>: Standing Orders signed, sites operating under a
                verified invoked stage, dust-generating activity categories restricted, and
                workers issued a Parchi.
              </p>
              <p>
                They do <span className="text-danger">not</span> establish that ambient air
                quality improved because of Aadesh&apos;s use. Aadesh records the execution of
                environmental restrictions and the associated operational impact. It does not
                independently measure PM2.5, estimate tonnes of emissions avoided, or claim a
                causal improvement in AQI.
              </p>
              <p className="border border-accent/40 bg-accent/10 p-3 text-accent">
                {data.claim_boundary}
              </p>
            </div>
          </Panel>

          {/* data and limitations */}
          <Panel
            title="Data and limitations"
            subtitle="Honest about what is verified, replayed, synthetic, or not yet measured"
          >
            <div className="space-y-3 text-sm">
              <div className="border border-line bg-panel p-4">
                <h3 className="font-semibold text-ink">The corpus behind this view</h3>
                <p className="mt-2 text-dim">{data.data_note}</p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="border border-line bg-panelAlt p-4">
                  <h3 className="font-semibold text-ink">Historical replay</h3>
                  <p className="mt-1 text-dim">
                    The Stage III invocation on 16 January 2026 and its revocation on 22
                    January 2026 are the only invoked stage records in the shipped corpus.
                    They are shown here as a historical scenario, never as a current
                    restriction.
                  </p>
                </div>
                <div className="border border-line bg-panelAlt p-4">
                  <h3 className="font-semibold text-ink">Synthetic observations</h3>
                  <p className="mt-1 text-dim">
                    The air quality reading is a synthetic placeholder. No live station
                    ingest exists yet, so the reading is labelled synthetic rather than
                    passed off as a measurement.
                  </p>
                </div>
              </div>

              <div className="border border-line bg-panelAlt p-4">
                <h3 className="font-semibold text-ink">Demo worker counts</h3>
                <p className="mt-1 text-dim">
                  The demonstration roster of 34 workers and the registration-readiness count
                  of 27 are demonstration data. They are not a measured count of affected
                  workers across Delhi-NCR, and worker count is never multiplied into an
                  entitlement amount.
                </p>
              </div>

              <div className="border border-danger/40 bg-danger/10 p-4">
                <h3 className="font-semibold text-danger">Privacy boundary</h3>
                <p className="mt-1 text-sm text-dim">
                  This public endpoint exposes aggregate operational information only. It does
                  not expose worker names, IDs, phone numbers, addresses, QR tokens,
                  acknowledgement secrets, individual Parchi records, or compensation
                  information. Low-count aggregates are presented with their derivation so
                  that small numbers cannot be mistaken for individual detail.
                </p>
              </div>
            </div>
          </Panel>

          {/* empty state */}
          {!data.is_current_invocation &&
            data.metrics.sites_with_active_standing_orders.count === 0 &&
            data.metrics.sites_acknowledging_regulated_halts.count === 0 &&
            data.metrics.dust_activities_halted.count === 0 &&
            data.metrics.workers_with_documented_displacement.count === 0 && (
              <Panel title="No qualifying data" subtitle="Empty state">
                <p className="text-sm leading-relaxed text-dim">
                  No verified current invocation, active Standing Order, applicable
                  dust-generating restriction, or issued Parchi is present in the current
                  demo state. The metrics above show the unavailable state honestly rather
                  than inventing values.
                </p>
                <p className="mt-3 text-xs text-faint">
                  Switch the supervisor console to the Stage III replay to see how a real
                  invocation flows through the system.
                </p>
              </Panel>
            )}

          <Panel className="mt-6" title="Navigate" subtitle="Return to the operational console">
            <div className="flex flex-wrap gap-3">
              <Button
                variant="secondary"
                onClick={load}
                disabled={busy}
              >
                <IconCheck className="h-4 w-4" />
                {busy ? "Refreshing…" : "Refresh this view"}
              </Button>
              <a href="/supervisor" className="inline-flex items-center gap-2 border border-lineStrong bg-panelAlt px-3 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent">
                Supervisor console <IconArrow className="h-4 w-4" />
              </a>
              <a href="/" className="inline-flex items-center gap-2 border border-lineStrong bg-panelAlt px-3 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent">
                Overview <IconArrow className="h-4 w-4" />
              </a>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
