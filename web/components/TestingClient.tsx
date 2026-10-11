"use client";

import { useEffect, useRef, useState } from "react";
import type { SupervisorPayload } from "@/lib/types";
import { getJson, failureOf, type ApiFailure } from "@/lib/api";
import { OperationsWorkspace } from "@/components/OperationsWorkspace";

export default function TestingClient() {
  const [data, setData] = useState<SupervisorPayload | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    let alive = true;
    getJson<SupervisorPayload>("/api/supervisor?scenario=replay&reading=aligned")
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setError(failureOf(err));
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div style={{ padding: "1rem" }}>
      <OperationsWorkspace
        payload={data}
        error={error ?? null}
        selectedObject={null}
        onSelectObject={() => {}}
        onCloseInspector={() => {}}
        activeWorkspaceView="site"
        onNavigateView={() => {}}
        onOpenWorkers={() => {}}
      />
    </div>
  );
}
