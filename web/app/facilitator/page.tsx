"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote, IconLock, IconShield, KeyValue, Loading, Panel, Pill } from "@/components/ui";
import { getJson, postJson } from "@/lib/api";
import { formatInstant } from "@/lib/format";
import type { FacilitatorPayload } from "@/lib/types";

export default function FacilitatorPage() {
  const [data, setData] = useState<FacilitatorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      await postJson("/api/standing-order", { scenario: "replay" });
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
        <div className="label">Facilitator · union rep / NGO caseworker</div>
        <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight">
          Help with a claim, without the worker&apos;s record
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-dim">
          A facilitator may assist with a claim the worker explicitly shared — and still cannot
          read the worker&apos;s Parchi. Opting in to help is not opting in to full disclosure.
          Everything shown below is an id, a state or an instant.
        </p>
      </header>

      {error && <div className="mt-5"><ErrorNote>{error}</ErrorNote></div>}
      {!data && !error && <Loading label="Building the redacted assist view" />}

      {data && (
        <div className="mt-6 space-y-6">
          <Panel
            title="AssistClaim — redacted view"
            subtitle="Authorized against a live worker consent, never against the Parchi."
            actions={<Pill tone="ok">Allowed</Pill>}
          >
            {view ? (
              <dl>
                <KeyValue k="Context">{view.context_id}</KeyValue>
                <KeyValue k="Parchi ref">{view.parchi_id}</KeyValue>
                <KeyValue k="Worker">{view.worker_id}</KeyValue>
                <KeyValue k="Site">{view.site_id}</KeyValue>
                <KeyValue k="Claim status">{view.claim_status}</KeyValue>
                <KeyValue k="Consent">{view.consent_status}</KeyValue>
                <KeyValue k="Granted">{formatInstant(view.consent_granted_at)}</KeyValue>
                <KeyValue k="Expires">{formatInstant(view.consent_expires_at)}</KeyValue>
              </dl>
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
