"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, IconLock, IconShield, KeyValue, Loading, Panel, Pill } from "@/components/ui";
import { getJson } from "@/lib/api";
import { formatInstant } from "@/lib/format";
import type { FacilitatorPayload } from "@/lib/types";

export default function FacilitatorPage() {
  const [data, setData] = useState<FacilitatorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getJson<FacilitatorPayload>("/api/facilitator"));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const view = data?.assistance?.view;

  return (
    <div className="mx-auto max-w-4xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="border-b border-line pb-5">
        <div className="label">Facilitator · local demonstration</div>
        <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight">
          Help with a claim, without the worker&apos;s record
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-dim">
          This local preview demonstrates a redacted assistance decision and its access limits.
          It does not collect live worker consent: this demo has no authenticated worker session.
          In a deployed workflow, only the worker may grant or revoke time-limited consent.
        </p>
      </header>

      <section className="mt-5 border border-line bg-panel p-4" aria-labelledby="consent-lifecycle-title">
        <div className="label">Worker-controlled access</div>
        <h2 id="consent-lifecycle-title" className="mt-1 text-base font-semibold text-ink">Consent has a clear end</h2>
        <ol className="mt-4 grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["01 · REQUEST", "Ask for assistance", "A request gives the facilitator no access."],
            ["02 · WORKER CHOICE", "Worker grants consent", "Only the named worker can grant it."],
            ["03 · LIMITED WINDOW", "Assist with one claim", "Cedar permits a redacted claim view only while consent is valid."],
            ["04 · REVOKED OR EXPIRED", "Access ends", "Withdrawal or expiry denies further assistance."],
          ].map(([step, title, body]) => (
            <li key={step} className="bg-panelAlt p-3">
              <span className="data text-[10px] text-accent">{step}</span>
              <strong className="mt-1 block text-sm text-ink">{title}</strong>
              <p className="mt-1 text-xs leading-relaxed text-dim">{body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-faint">This page shows a local authorization demonstration; its sample grant is not a worker’s live consent.</p>
      </section>

      {error && <div className="mt-5"><ErrorNote>{error}</ErrorNote></div>}
      {!data && !error && <Loading label="Building the redacted assist view" />}

      {data && (
        <div className="mt-6 space-y-6">
          {data.error ? (
            <Panel title="No demonstration record yet" subtitle="The facilitator view does not create a Standing Order or Parchi when opened.">
              <p className="text-sm text-dim">{data.error}</p>
              <a href="/supervisor" className="mt-4 inline-flex border border-lineStrong bg-panelAlt px-3 py-2 text-sm text-ink hover:border-accent">Open supervisor demonstration ↗</a>
            </Panel>
          ) : (
            <>
          <Panel
            title="AssistClaim — redacted demo view"
            subtitle="Seeded consent scenario · Cedar decision is real · worker consent is not live or user-granted."
            actions={<Pill tone="warn">Simulated consent</Pill>}
          >
            {view ? (
              <>
                <dl>
                <KeyValue k="Claim status">{view.claim_status}</KeyValue>
                <KeyValue k="Consent">{view.consent_status} · demo fixture</KeyValue>
                <KeyValue k="Granted">{formatInstant(view.consent_granted_at)}</KeyValue>
                <KeyValue k="Expires">{formatInstant(view.consent_expires_at)}</KeyValue>
                </dl>
                <details className="mt-4 border-t border-line pt-3">
                  <summary className="cursor-pointer text-xs text-dim">Technical references</summary>
                  <dl className="mt-3">
                    <KeyValue k="Context">{view.context_id}</KeyValue>
                    <KeyValue k="Parchi reference">{view.parchi_id}</KeyValue>
                    <KeyValue k="Worker reference">{view.worker_id}</KeyValue>
                    <KeyValue k="Site reference">{view.site_id}</KeyValue>
                  </dl>
                </details>
              </>
            ) : (
              <p className="text-sm text-dim">{data.assistance?.reason ?? "No assistance view."}</p>
            )}
            <div className="mt-4 grid gap-2 text-xs text-faint sm:grid-cols-3">
              {[
                "No worker name",
                "No phone number",
                "No Aadhaar",
                "No bank details",
                "No full Parchi",
                "No raw QR token",
              ].map((x) => (
                <span key={x} className="flex items-center gap-1.5">
                  <IconLock className="h-3 w-3 text-faint" /> {x}
                </span>
              ))}
            </div>
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <DecisionCard
              title="Facilitator attempts ViewParchi"
              decision={data.read_attempt}
            />
            <DecisionCard
              title="AssistClaim with a consent never granted"
              decision={data.ungranted_consent_attempt}
            />
          </div>
          <p className="text-xs leading-relaxed text-faint">The access decision and redaction rules are exercised through the backend authorization service. Consent grant, expiry and revocation are enforced by the core model; this preview does not let a facilitator create or revoke a worker&apos;s consent.</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DecisionCard({
  title,
  decision,
}: {
  title: string;
  decision?: FacilitatorPayload["read_attempt"];
}) {
  if (!decision) return null;
  const denied = !decision.allowed;
  return (
    <Panel title={title} actions={<Pill tone={denied ? "danger" : "ok"}>{denied ? "Denied" : "Allowed"}</Pill>}>
      <div className="flex items-start gap-2">
        <IconShield className={`mt-0.5 h-4 w-4 shrink-0 ${denied ? "text-danger" : "text-success"}`} />
        <div>
          <p className="data text-[12px] text-faint">action: {decision.attempted}</p>
          <p className="mt-1 text-sm text-ink">{decision.reason}</p>
          {decision.policy_id && (
            <p className="data mt-2 text-[11px] text-faint">deciding policy: {decision.policy_id}</p>
          )}
        </div>
      </div>
    </Panel>
  );
}
