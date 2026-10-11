"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, Loading } from "@/components/ui";
import { SiteSceneExplorer } from "@/components/SiteSceneExplorer";
import { getJson, failureOf } from "@/lib/api";
import { formatInstant } from "@/lib/format";
import type { FacilitatorPayload } from "@/lib/types";

type Station = "consent" | "summary" | "requirements" | "source" | "outcome";
const STATIONS: { id: Station; number: string; title: string; detail: string }[] = [
  { id: "consent", number: "01", title: "Consent", detail: "Authorization check" },
  { id: "summary", number: "02", title: "Case summary", detail: "Redacted view" },
  { id: "requirements", number: "03", title: "Requirements", detail: "Not returned" },
  { id: "source", number: "04", title: "Source guidance", detail: "Not returned" },
  { id: "outcome", number: "05", title: "Outcome", detail: "No write action" },
];

export default function FacilitatorPage() {
  const [data, setData] = useState<FacilitatorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [station, setStation] = useState<Station>("consent");
  const [lastChecked, setLastChecked] = useState<string | null>(null);
  const requestId = useRef(0);
  const view = data?.assistance?.view;
  const allowed = Boolean(data?.assistance?.allowed && view);
  const demo = process.env.NEXT_PUBLIC_AADESH_DEMO === "1";

  const refresh = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setData(null); // remove formerly permitted data before checking current authorization
    setBusy(true);
    setError(null);
    try {
      const result = await getJson<FacilitatorPayload>("/api/facilitator");
      if (currentRequest === requestId.current) { setData(result); setLastChecked(new Date().toISOString()); }
    } catch (err) {
      if (currentRequest === requestId.current) { setData(null); setError(failureOf(err).message); }
    } finally { if (currentRequest === requestId.current) setBusy(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!allowed) return;
    const id = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 30_000);
    const expiresAt = data?.assistance?.view?.consent_expires_at;
    const expiryTimer = expiresAt ? window.setTimeout(() => void refresh(), Math.max(0, Date.parse(expiresAt) - Date.now())) : undefined;
    const onVisibility = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { window.clearInterval(id); if (expiryTimer) window.clearTimeout(expiryTimer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [allowed, data?.assistance?.view?.consent_expires_at, refresh]);

  const denial = data?.assistance?.reason || data?.error || (demo ? "The demonstration API has no worker-granted consent for this request." : "No currently authorized assistance request was returned.");

  return <main className="assist-shell">
    <header className="assist-header">
      <div className="assist-brand"><span className="assist-mark">A</span><span>AADHESH <i>/ ASSISTANCE STUDIO</i></span></div>
      <div className="assist-header-state"><span className={allowed ? "assist-dot is-authorized" : "assist-dot"} />{allowed ? "AUTHORIZED VIEW" : "CONSENT REQUIRED"}</div>
    </header>

    <section className="assist-intro">
      <div><p className="label">FACILITATOR WORKSPACE / ASSISTANCE ONLY</p><h1>Help move one step forward.</h1><p>Review only the case fields the backend permits. The worker keeps control of their Parchi and consent.</p></div>
      <button type="button" className="assist-refresh" onClick={() => void refresh()} disabled={busy} aria-label="Recheck authorization"><span aria-hidden="true">↻</span> Recheck access</button>
    </section>

    <div className="assist-workspace">
      <aside className="assist-queue" aria-label="Assistance request queue">
        <div className="assist-queue-heading"><div><span className="label">REQUEST QUEUE</span><h2>Current access</h2></div><span className="assist-queue-count">{allowed ? "01" : "00"}</span></div>
        <div className={`assist-case ${allowed ? "is-selected" : "is-denied"}`} aria-current="true">
          <div className="assist-case-icon" aria-hidden="true">{allowed ? "↗" : "—"}</div><div><strong>{allowed ? "Permitted case" : "No permitted case"}</strong><small>{allowed ? "Redacted assistance scope" : "No protected case details"}</small></div><span className="assist-case-status">{allowed ? "OPEN" : "WAIT"}</span>
        </div>
        {!allowed && <p className="assist-queue-note">The API provides a single current request, not a browsable queue. No worker or Parchi identifiers are shown before access is permitted.</p>}
        <div className="assist-queue-foot"><span>SERVER DECISION</span><b>{allowed ? "ALLOW" : data ? "DENY" : "PENDING"}</b></div>
      </aside>

      <section className="assist-main" aria-label="Guided assistance workflow">
        <div className="assist-scene-heading"><div><span className="label">GUIDED WORKSPACE</span><h2>Assistance pathway</h2></div><span className="assist-time">{lastChecked ? `CHECKED ${formatInstant(lastChecked)}` : "CHECKING…"}</span></div>
        <p className="assist-quiet">Illustrative site context only. No site survey, zone-level rule, or authorized case is implied by this geometry.</p>
        <SiteSceneExplorer title="Illustrative site context" label="SITE CONTEXT / 3D MODEL" />
        <div className="assist-stations" role="group" aria-label="Assistance stages">
          {STATIONS.map((item, i) => <button type="button" key={item.id} onClick={() => setStation(item.id)} aria-pressed={station === item.id} className={station === item.id ? "is-active" : ""}>
            <span className="assist-station-number">{item.number}</span><b>{item.title}</b><small>{item.detail}</small>{i < STATIONS.length - 1 && <span className="assist-station-link" aria-hidden="true">···</span>}
          </button>)}
        </div>

        <div className="assist-detail">
          <div className="assist-detail-kicker"><span className="label">{STATIONS.find((item) => item.id === station)?.number} / {STATIONS.find((item) => item.id === station)?.title}</span><span className={`assist-permission ${allowed ? "is-allowed" : ""}`}>{allowed ? "PERMITTED" : "NOT PERMITTED"}</span></div>
          {busy && !data ? <Loading label="Checking worker consent with the authorization service" /> : error ? <div className="assist-error"><ErrorNote>{error}</ErrorNote><button type="button" onClick={() => void refresh()}>Retry authorization check</button></div> : !data ? <p className="assist-quiet">Waiting for authorization response…</p> : !allowed ? <div className="assist-denial" role="status"><span className="assist-denial-symbol" aria-hidden="true">!</span><div><h3>Worker consent is required</h3><p>{denial}</p><p className="assist-quiet">Ask the worker to open their own Parchi and choose whether to allow assistance. Facilitators cannot grant consent.</p></div></div> : <AllowedStation station={station} view={view!} />}
        </div>

        <p className="assist-boundary"><span aria-hidden="true">◈</span> Consent is checked by the backend on each refresh. When it is revoked or expires, this workspace clears the previous view before requesting access again.</p>
      </section>
    </div>
    <footer className="assist-footer"><span>ASSISTANCE STUDIO</span><span>NO FULL PARCHI · NO PROXY ACKNOWLEDGEMENT · NO CLAIM FILING</span></footer>
  </main>;
}

function AllowedStation({ station, view }: { station: Station; view: NonNullable<NonNullable<FacilitatorPayload["assistance"]>["view"]> }) {
  if (station !== "summary") {
    const notices: Record<Exclude<Station, "summary">, { title: string; body: string }> = {
      consent: { title: "Consent validated", body: "The backend returned a permitted, time-limited assistance view. The grant time and expiry below come from the server." },
      requirements: { title: "Requirement details are unavailable", body: "The facilitator response does not include missing documentation or requirement statuses. No checklist can be completed here." },
      source: { title: "Source citations are unavailable", body: "This redacted facilitator response includes no official citations or source excerpts. Open the worker’s own Parchi with them for source review." },
      outcome: { title: "No completion operation is available", body: "There is no facilitator action endpoint for recording assistance completion or claim outcomes. This screen does not simulate one." },
    };
    const message = notices[station];
    return <div className="assist-capability"><span className="assist-capability-mark" aria-hidden="true">{station === "consent" ? "✓" : "—"}</span><div><h3>{message.title}</h3><p>{message.body}</p></div></div>;
  }
  return <div className="assist-summary"><div className="assist-summary-intro"><div className="assist-redacted-avatar" aria-hidden="true">◌</div><div><span className="label">BACKEND-REDACTED CASE VIEW</span><h3>Permitted case summary</h3></div></div>
    <dl><div><dt>Claim status</dt><dd>{view.claim_status}</dd></div><div><dt>Consent status</dt><dd>{view.consent_status}</dd></div><div><dt>Granted</dt><dd>{formatInstant(view.consent_granted_at)}</dd></div><div><dt>Expires</dt><dd>{formatInstant(view.consent_expires_at)}</dd></div></dl>
    <p className="assist-quiet">Personal identity, phone, Aadhaar, bank details, full Parchi, obligation list and source quotations are not part of this view.</p>
  </div>;
}
