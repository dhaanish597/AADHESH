"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, ErrorNote, IconLock, IconShield, KeyValue, Loading, Panel, Pill } from "@/components/ui";
import { postJson } from "@/lib/api";
import type { CedarDecision } from "@/lib/types";

export default function CedarPage() {
  const [ready, setReady] = useState(false);
  const [decision, setDecision] = useState<CedarDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const prepare = useCallback(async () => {
    setError(null);
    try {
      await postJson("/api/standing-order", { scenario: "replay" });
      setReady(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void prepare();
  }, [prepare]);

  const attempt = async () => {
    setBusy(true);
    setError(null);
    try {
      setDecision(
        await postJson<CedarDecision>("/api/cedar/supervisor-acknowledge", {
          worker_id: "worker-002",
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="border-b border-line pb-5">
        <div className="label">Authority · Cedar 4.x</div>
        <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight">
          Who is allowed to do this?
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-dim">
          Every read and write crosses a real Cedar authorization boundary, evaluated in-process
          from <span className="data">infra/cedar/policies.cedar</span>. The rules below are
          product behaviour, not decoration: a halt record is incomplete until the people it
          displaced confirm it themselves.
        </p>
      </header>

      {error && <div className="mt-5"><ErrorNote>{error}</ErrorNote></div>}

      <Panel
        className="mt-6"
        title="A supervisor attempts to acknowledge a worker's Parchi"
        subtitle="Principal: supervisor-001 (role: supervisor) · action: AcknowledgeOwnParchi"
      >
        <dl className="mb-4">
          <KeyValue k="Resource">Parchi for worker-002 (pending acknowledgement)</KeyValue>
          <KeyValue k="Policy">@id(“no-proxy-acknowledgement”)</KeyValue>
        </dl>
        <Button onClick={attempt} disabled={!ready || busy} variant="danger">
          <IconLock className="h-4 w-4" />
          {busy ? "Evaluating…" : "Acknowledge worker"}
        </Button>
        {!ready && !error && <Loading label="Preparing a pending parchi" />}

        {decision && (
          <div className="mt-5">
            {decision.allowed ? (
              <Pill tone="ok">Allowed</Pill>
            ) : (
              <div className="border border-danger/50 bg-danger/10 p-4">
                <div className="flex items-center gap-2">
                  <IconShield className="h-5 w-5 text-danger" />
                  <span className="data text-sm font-bold uppercase tracking-[0.14em] text-danger">
                    Denied
                  </span>
                </div>
                <p className="mt-2 text-sm text-ink">{decision.reason}</p>
                {decision.policy_id && (
                  <p className="data mt-2 text-[11px] text-faint">
                    deciding policy: {decision.policy_id}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </Panel>

      <Panel className="mt-6" title="Why this is enforced twice">
        <p className="text-sm leading-relaxed text-dim">
          Cedar refuses the request at the boundary. The domain refuses it again inside{" "}
          <span className="data">aadesh_core.parchi.acknowledge</span>, which rejects any actor who
          is not the worker named on the record. That redundancy is deliberate: a security
          property enforced in exactly one place is one refactor away from not existing.
        </p>
      </Panel>
    </div>
  );
}
