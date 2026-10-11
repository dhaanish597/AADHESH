"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button, ErrorNote, Loading } from "@/components/ui";
import { SiteSceneExplorer } from "@/components/SiteSceneExplorer";
import { ApiError, postJson } from "@/lib/api";
import { authConfigured, readSession, signIn } from "@/lib/auth";
import { formatInstant, stageName } from "@/lib/format";
import type { WorkerView } from "@/lib/types";

type Lang = "hi" | "en";
type Step = "change" | "reason" | "source" | "next" | "ack";
type ConsentResult = { context_id: string; consent_granted: boolean; granted_at: string; expires_at: string; revoked_at: string | null };
const CONSENT_KEY = "aadesh.worker.consent-reference";

const WORDS = {
  hi: {
    title: "आपकी पर्ची, आपके अगले कदम", sub: "अपनी पर्ची समझें। पुष्टि केवल आप अपने लिए करें।", loading: "आपकी पर्ची खोली जा रही है…", retry: "फिर कोशिश करें",
    change: "क्या दर्ज है?", reason: "यह काम से कैसे जुड़ता है?", source: "सरकारी स्रोत", next: "अब क्या करें?", ack: "मेरी पुष्टि",
    schematic: "साइट का सांकेतिक दृश्य", schematicNote: "ये केवल साइट-स्तर के रिकॉर्ड को समझाने वाले सांकेतिक क्षेत्र हैं। ये अलग-अलग कानूनी निर्णय या लाइव माप नहीं हैं।", historicalSourceNote: "ऐतिहासिक रिकॉर्ड के लिए वर्तमान अनुसूची का उद्धरण केवल स्रोत दिखाने का उदाहरण है; यह प्रमाण नहीं है कि यही धारा उस समय लागू थी।",
    site: "आपकी साइट", activity: "काम का विवरण", stage: "दर्ज GRAP चरण", provenance: "रिकॉर्ड का स्रोत", historical: "ऐतिहासिक प्रदर्शन रिकॉर्ड · वर्तमान रोक नहीं", synthetic: "सिंथेटिक प्रदर्शन रिकॉर्ड · लाइव माप नहीं", unknown: "इस पर्ची में जानकारी उपलब्ध नहीं है।", sourceMissing: "इस रिकॉर्ड में कोई सरकारी उद्धरण उपलब्ध नहीं है।",
    checklist: "तैयारी की जानकारी", checklistEmpty: "इस पर्ची में कोई तैयारी सूची उपलब्ध नहीं है। कोई अतिरिक्त ज़रूरत यहाँ से अनुमानित नहीं की गई है।", checklistNote: "दिखाई गई चीज़ें केवल पर्ची से मिली हैं। इस स्क्रीन पर उन्हें पूरा घोषित करने की सुविधा नहीं है।",
    pending: "आपकी पुष्टि बाकी है", acked: "पुष्टि सर्वर पर दर्ज है", acknowledge: "मैंने अपनी पर्ची देखी है", acknowledgedAt: "सर्वर पर दर्ज समय", expired: "यह QR लिंक अब मान्य नहीं है। अपने साइट सुपरवाइज़र से नया व्यक्तिगत लिंक लें।", invalid: "यह लिंक मान्य नहीं है। व्यक्तिगत QR लिंक दोबारा स्कैन करें।", rejected: "यह लिंक अमान्य, समाप्त, या पहले उपयोग किया हुआ हो सकता है। पहचान सुरक्षित रखने के लिए सर्वर इन स्थितियों में अंतर नहीं बताता। नया व्यक्तिगत QR लें।", wrongWorker: "यह पर्ची इस लिंक के लिए अधिकृत नहीं है। साइट सुपरवाइज़र से सहायता लें।",
    help: "सहायता चाहिए?", helpDesc: "आप चाहें तो किसी फ़ैसिलिटेटर को केवल सीमित दावा-सहायता के लिए समय-सीमित अनुमति दे सकते हैं। आपकी पर्ची साझा नहीं होगी।", grant: "सहायता की अनुमति दें", revoke: "अनुमति वापस लें", consent: "अनुमति की स्थिति", expires: "अनुमति समाप्त होगी", grantOk: "सर्वर ने सहायता-अनुमति दर्ज की।", revokeOk: "सर्वर ने अनुमति वापस लेने की पुष्टि की।", noAuth: "यह कार्य आपकी अपनी worker पहचान से साइन-इन होने पर ही उपलब्ध है।", localConsent: "स्थानीय डेमो में अनुमति मेमोरी में रहती है; सर्वर रीस्टार्ट पर मिट जाती है। यह AWS में स्थायी अनुमति का प्रमाण नहीं है।", noConsentLookup: "पहले दी गई अनुमति की स्थिति यहाँ पढ़ने का API उपलब्ध नहीं है।", legal: "यह सरकारी आवेदन या कानूनी सलाह नहीं है। कोई दावा दाखिल नहीं होता।", noLink: "पर्ची लिंक नहीं मिला", scan: "अपनी व्यक्तिगत पर्ची खोलने के लिए साइट पर दिया गया QR स्कैन करें।", sourceOpen: "आधिकारिक स्रोत खोलें", refs: "रिकॉर्ड संदर्भ", retryLoad: "पर्ची फिर खोलें", ackError: "पुष्टि दर्ज नहीं हो सकी। नीचे दी गई त्रुटि देखें।",
  },
  en: {
    title: "Your Parchi, your next steps", sub: "Understand your Parchi. Confirm it only for yourself.", loading: "Opening your Parchi…", retry: "Try again",
    change: "What is recorded?", reason: "How does it relate to this activity?", source: "Official source", next: "What can I do next?", ack: "My confirmation",
    schematic: "Schematic site view", schematicNote: "These are schematic zones for the site-level record only. They are not separate legal decisions or live readings.", historicalSourceNote: "For a historical record, a citation from the current schedule is shown only as a source example; it does not prove that the same clause applied at that time.",
    site: "Your site", activity: "Activity on record", stage: "Recorded GRAP stage", provenance: "Record provenance", historical: "Historical demonstration record · not a current restriction", synthetic: "Synthetic demonstration record · not a live measurement", unknown: "Information is not available in this Parchi.", sourceMissing: "No official quotation is available in this record.",
    checklist: "Readiness information", checklistEmpty: "This Parchi has no readiness checklist. No additional requirements are inferred here.", checklistNote: "Items come from the Parchi only. This screen cannot mark them complete.",
    pending: "Your confirmation is pending", acked: "Confirmation recorded by the server", acknowledge: "I have reviewed my Parchi", acknowledgedAt: "Server recorded at", expired: "This QR link is no longer valid. Ask your site supervisor for a new personal link.", invalid: "This link is not valid. Scan your personal QR link again.", rejected: "This link may be invalid, expired, or already used. The server does not distinguish these states to protect identity. Ask for a new personal QR.", wrongWorker: "This Parchi is not authorized for this link. Ask your site supervisor for help.",
    help: "Need assistance?", helpDesc: "You may give a facilitator time-limited permission to help with a claim only. Your Parchi is not shared.", grant: "Allow assistance", revoke: "Revoke permission", consent: "Permission status", expires: "Permission expires", grantOk: "The server recorded your assistance permission.", revokeOk: "The server confirmed permission was revoked.", noAuth: "This action requires signing in with your own worker identity.", localConsent: "In the local demo, permission is held in memory and is lost when the server restarts. This does not demonstrate durable AWS consent.", noConsentLookup: "There is no API here to read an earlier permission's status.", legal: "This is not a government application or legal advice. No claim is filed.", noLink: "No Parchi link", scan: "Scan the personal QR provided at your site to open your Parchi.", sourceOpen: "Open official source", refs: "Record references", retryLoad: "Reload Parchi", ackError: "Confirmation could not be recorded. See the message below.",
  },
} satisfies Record<Lang, Record<string, string>>;

function readPayload() {
  if (typeof window === "undefined") return "";
  const incoming = new URLSearchParams(window.location.hash.slice(1)).get("payload") ?? "";
  if (incoming) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  return incoming;
}

export default function WorkerPage() {
  const [payload, setPayload] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [lang, setLang] = useState<Lang>("hi");
  const [view, setView] = useState<WorkerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeStep, setActiveStep] = useState<Step>("change");
  const [consent, setConsent] = useState<ConsentResult | null>(null);
  const [consentClock, setConsentClock] = useState(0);

  useEffect(() => {
    setPayload(readPayload());
    // The API locator may include worker/Parchi identifiers. Keep it in page memory only;
    // without a consent-status lookup endpoint, a reload must return to the unknown state.
    try { sessionStorage.removeItem(CONSENT_KEY); } catch { /* storage may be disabled */ }
  }, []);
  useEffect(() => {
    const now = Date.now();
    setConsentClock(now);
    if (!consent) return;
    const expiry = Date.parse(consent.expires_at);
    const timer = window.setTimeout(() => setConsentClock(Date.now()), Math.max(0, expiry - now));
    return () => window.clearTimeout(timer);
  }, [consent]);

  const load = useCallback(async (current = payload) => {
    if (!current) { setView(null); setError(null); return; }
    setBusy(true); setError(null); setNotice(null);
    setView(null);
    try { setView(await postJson<WorkerView>("/api/worker/view", { payload: current })); }
    catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const status = err instanceof ApiError ? err.status : 0;
      setError(status === 410 ? WORDS[lang].expired : status === 400 && /acknowledgement link/i.test(message) ? WORDS[lang].rejected : /wrong worker|worker identity|can only be acknowledged by the worker/i.test(message) ? WORDS[lang].wrongWorker : message);
    } finally { setBusy(false); }
  }, [lang, payload]);

  useEffect(() => { if (payload) void load(payload); }, [payload, load]);
  const t = WORDS[lang];
  const acknowledged = view?.state === "acknowledged" || view?.state === "sealed" || view?.status === "ACKNOWLEDGED";
  const replay = view?.provenance === "replay";
  const consentActive = Boolean(consent && !consent.revoked_at && Date.parse(consent.expires_at) > (consentClock || Date.now()));
  const citations = view?.citations ?? [];
  const stages = useMemo(() => [
    ["change", t.change], ["reason", t.reason], ["source", t.source], ["next", t.next], ["ack", t.ack],
  ] as [Step, string][], [t]);

  const acknowledge = async () => {
    if (!payload || !view?.worker_id) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await postJson("/api/worker/acknowledge", { payload, worker_id: view.worker_id });
      const confirmed = await postJson<WorkerView>("/api/worker/view", { payload });
      setView(confirmed);
      const confirmedAck = confirmed.state === "acknowledged" || confirmed.state === "sealed" || confirmed.status === "ACKNOWLEDGED";
      if (confirmedAck) setNotice(`${t.acked}${confirmed.acknowledged_at ? ` · ${formatInstant(confirmed.acknowledged_at)}` : ""}`);
      else setError(lang === "hi" ? "सर्वर ने अभी पुष्टि दर्ज होने की सूचना नहीं दी।" : "The server has not confirmed the acknowledgement yet.");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };

  const doConsent = async (revoke = false) => {
    if (!view || !consent && revoke) return;
    const session = readSession();
    if (authConfigured && (!session || session.role !== "worker" || session.principalId !== view.worker_id)) { setError(t.noAuth); return; }
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = revoke
        ? await postJson<ConsentResult>("/api/consent/revoke", { context_id: consent!.context_id })
        : await postJson<ConsentResult>("/api/consent/grant", { parchi_id: view.parchi_id, worker_id: view.worker_id });
      setConsent(result);
      try {
        // Store only a display receipt. The API context locator stays in page memory so it
        // cannot expose worker/Parchi identifiers through browser storage.
        sessionStorage.setItem(CONSENT_KEY, JSON.stringify({
          consent_granted: result.consent_granted,
          granted_at: result.granted_at,
          expires_at: result.expires_at,
          revoked_at: result.revoked_at,
        }));
      } catch { /* keep the server response in this page's state */ }
      setNotice(revoke ? t.revokeOk : t.grantOk);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };

  return <main className="worker-route worker-shell" lang={lang}>
    <div className="worker-top"><Link href="/" className="worker-brand">AADHESH <span>/ WORKER</span></Link><LanguageToggle lang={lang} setLang={setLang} /></div>
    <header className="worker-hero"><div><p className="label">MY WORKSITE <span>·</span> MY PARCHI</p><h1>{t.title}</h1><p>{t.sub}</p></div><div className="worker-record-tag"><span className="worker-live-dot" />{view ? view.state.replaceAll("_", " ") : payload ? "CHECKING LINK" : "NO LINK"}</div></header>
    {error && <div className="worker-alert" role="alert"><ErrorNote>{error}</ErrorNote><button type="button" onClick={() => void load()}>{t.retry}</button></div>}
    {notice && <div className="worker-confirmation" role="status"><span aria-hidden="true">✓</span>{notice}</div>}
    {!view && !error && payload && <div className="worker-loading"><Loading label={t.loading} /></div>}
      <nav className="worker-journey" aria-label={lang === "hi" ? "पर्ची समझने के चरण" : "Parchi journey"}>
        {stages.map(([key, label], i) => <button type="button" key={key} aria-current={activeStep === key ? "step" : undefined} className={activeStep === key ? "is-active" : ""} onClick={() => { setActiveStep(key); document.getElementById(`worker-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}><span>{String(i + 1).padStart(2, "0")}</span>{label}</button>)}
      </nav>

      <div className="worker-layout">
        <div className="worker-primary">
          <SiteSceneExplorer locale={lang} title={lang === "en" ? "Illustrative construction site" : "निर्माण साइट का सांकेतिक दृश्य"} label="01 / SITE EXPLORER" />
          {!view && <section className="worker-empty" aria-label={t.noLink}><div className="worker-empty-mark">P</div><p className="label">PERSONAL RECORD</p><h2>{payload ? (lang === "hi" ? "पर्ची नहीं खुली" : "Parchi not open") : t.noLink}</h2><p>{error ? (lang === "hi" ? "अपनी पर्ची खोलने के लिए नया व्यक्तिगत QR लिंक दर्ज करें।" : "Enter a new personal QR link to open your Parchi.") : t.scan}</p><form className="worker-token-form" onSubmit={(event) => { event.preventDefault(); const value = tokenInput.trim(); if (!value) return; setError(null); if (value === payload) void load(value); else setPayload(value); }}><label htmlFor="worker-token">{lang === "hi" ? "व्यक्तिगत QR लिंक / टोकन" : "Personal QR link / token"}</label><input id="worker-token" autoComplete="off" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="aadesh://ack/…" /><button type="submit" disabled={!tokenInput.trim() || busy}>{lang === "hi" ? "पर्ची खोलें" : "Open Parchi"}</button></form>{!payload && <Link href="/supervisor" className="worker-text-link">{lang === "hi" ? "साइट सुपरवाइज़र से व्यक्तिगत QR लें" : "Ask your site supervisor for your personal QR"}</Link>}</section>}
          {view ? <section className="worker-paper" id="worker-change">
            <div className="worker-paper-kicker"><span className="label">PARCHI / {view.parchi_id}</span><span className={`worker-state ${acknowledged ? "is-done" : ""}`}>{acknowledged ? t.acked : t.pending}</span></div>
            <h2>{t.change}</h2>
            {replay && <div className="worker-provenance worker-historical">{t.historical}. Stage III · invoked 16 Jan 2026 · revoked 22 Jan 2026.</div>}
            {view.provenance === "synthetic" && <div className="worker-provenance">{t.synthetic}</div>}
            <dl className="worker-facts">
              <Fact label={t.site} value={view.site_label || view.site_id || t.unknown} />
              <Fact label={t.stage} value={view.stage == null ? t.unknown : `GRAP ${stageName(view.stage)}`} />
              <Fact label={t.provenance} value={view.provenance || t.unknown} />
            </dl>
            {view.cites_measured_data === false && <p className="worker-provenance">{lang === "hi" ? "यह पर्ची लाइव स्टेशन माप पर आधारित नहीं है।" : "This Parchi is not based on a live station measurement."}</p>}
            <p className="worker-small-note">{lang === "hi" ? "कारण या क्षेत्र-स्तरीय असर का अतिरिक्त विवरण इस worker रिकॉर्ड में उपलब्ध नहीं है।" : "Further reason or zone-specific impact is not available in this worker record."}</p>
          </section> : <section className="worker-paper" id="worker-change"><div className="worker-paper-kicker"><span className="label">PERSONAL RECORD</span><span className="worker-state">{lang === "hi" ? "लिंक की प्रतीक्षा" : "AWAITING LINK"}</span></div><h2>{t.change}</h2><p className="worker-empty-inline">{lang === "hi" ? "यह केवल कार्यप्रवाह का परिचय है। कोई पर्ची, साइट स्थिति या व्यक्तिगत रिकॉर्ड लोड नहीं है।" : "This is a guide to the workflow only. No Parchi, site status, or personal record is loaded."}</p></section>}

          <section className="worker-reason" id="worker-reason">
            <div className="worker-section-heading"><div><span className="label">02 / EXPLANATION</span><h2>{t.reason}</h2></div><span className="worker-reason-mark" aria-hidden="true">?</span></div>
            <p>{view ? (lang === "hi" ? "इस पर्ची API में गतिविधि-विशिष्ट कारण या लागू शर्त का विवरण नहीं मिला। नीचे दिए गए उद्धरण ही उपलब्ध आधिकारिक स्रोत हैं; उनसे आगे कोई कानूनी निष्कर्ष नहीं जोड़ा गया है।" : "This Parchi API response does not include an activity-specific explanation or applicable-condition detail. The citations below are the official source details available; no further legal conclusion is inferred.") : (lang === "hi" ? "व्यक्तिगत पर्ची लिंक होने पर केवल उसी रिकॉर्ड की जानकारी दिखाई जाएगी।" : "Details from your own record appear after you link your personal Parchi.")}</p>
          </section>

          <section className="worker-source" id="worker-source">
            <div className="worker-section-heading"><div><span className="label">03 / EVIDENCE</span><h2>{t.source}</h2></div><span className="worker-source-count">{String(citations.length).padStart(2, "0")}</span></div>
            {!view || !citations.length ? <p className="worker-empty-inline">{view ? t.sourceMissing : (lang === "hi" ? "पर्ची लिंक होने पर इसके वास्तविक स्रोत दिखाई देंगे।" : "Your Parchi’s actual citations will appear after it is linked.")}</p> : citations.map((citation) => <article className="worker-citation" key={`${citation.obligation_id}-${citation.source_doc}`}>
              {replay && <p className="worker-provenance worker-historical">{t.historicalSourceNote}</p>}
              <div><span className="worker-citation-tag">{citation.obligation_id}</span><span className="worker-citation-page">{lang === "hi" ? "पृष्ठ" : "PAGE"} {citation.source_page}</span></div>
              <h3>{citation.source_title}</h3>
              <blockquote>{citation.source_quote}</blockquote>
              <div className="worker-citation-meta">{citation.source_doc} <span>·</span> SHA-256 {citation.source_hash || (lang === "hi" ? "उपलब्ध नहीं" : "unavailable")}</div>
              <a href={`${citation.source_url}#page=${citation.source_page}`} target="_blank" rel="noreferrer" className="worker-text-link">{t.sourceOpen} ↗</a>
            </article>)}
          </section>

          <section className="worker-next" id="worker-next">
            <div className="worker-section-heading"><div><span className="label">04 / READINESS</span><h2>{t.next}</h2></div><span className="worker-next-arrow">→</span></div>
            <h3>{t.checklist}</h3>
            {view?.readiness_checklist?.length ? <ul className="worker-readiness">{view.readiness_checklist.map((item, i) => <li key={`${item}-${i}`}><span aria-hidden="true">○</span><div>{item}<small>{lang === "hi" ? "पर्ची में दर्ज · पूर्णता की स्थिति उपलब्ध नहीं" : "listed in Parchi · completion status unavailable"}</small></div><b>{lang === "hi" ? "अज्ञात" : "UNKNOWN"}</b></li>)}</ul> : <p className="worker-empty-inline">{view ? t.checklistEmpty : (lang === "hi" ? "कोई व्यक्तिगत तैयारी सूची लोड नहीं है।" : "No personal readiness checklist is loaded.")}</p>}
            <p className="worker-small-note">{t.checklistNote}</p>
            <button type="button" className="worker-help-open" onClick={() => document.getElementById("worker-help")?.scrollIntoView({ behavior: "smooth", block: "center" })}><span>＋</span>{t.help}</button>
          </section>
        </div>

        <aside className="worker-side">{view ? <>
          <section className="worker-ack" id="worker-ack">
            <span className="label">05 / YOUR CHOICE</span>
            <div className="worker-ack-symbol" aria-hidden="true">{acknowledged ? "✓" : "✳"}</div>
            <h2>{acknowledged ? t.acked : t.acknowledge}</h2>
            {acknowledged ? <p>{t.acknowledgedAt}<strong>{formatInstant(view.acknowledged_at ?? view.sealed_at) || t.unknown}</strong></p> : <><p>{lang === "hi" ? "पर्ची देखने और समझने के बाद ही पुष्टि करें।" : "Confirm only after you have reviewed and understood the Parchi."}</p><Button onClick={() => void acknowledge()} disabled={busy} className="worker-ack-button">{busy ? "…" : t.acknowledge} <span>→</span></Button></>}
          </section>

          <section className="worker-help" id="worker-help">
            <span className="label">ASSISTANCE / OPTIONAL</span><h2>{t.help}</h2><p>{t.helpDesc}</p>
            {consent ? <div className="worker-consent-state"><span className={consentActive ? "is-on" : "is-off"} />{t.consent}: {consent.revoked_at ? (lang === "hi" ? "वापस ली गई" : "REVOKED") : !consentActive ? (lang === "hi" ? "समाप्त" : "EXPIRED") : (lang === "hi" ? "चालू" : "ACTIVE")}<small>{lang === "hi" ? "अनुमति समय" : "Granted"}: {formatInstant(consent.granted_at)}</small><small>{t.expires}: {formatInstant(consent.expires_at)}</small></div> : <p className="worker-small-note">{t.noConsentLookup}</p>}
            {authConfigured && (!readSession() || readSession()?.role !== "worker" || readSession()?.principalId !== view.worker_id) ? <button type="button" className="worker-outline-button" onClick={signIn}>{lang === "hi" ? "अपने worker खाते से साइन-इन" : "Sign in as this worker"}</button> : <div className="worker-consent-actions">
              {!consentActive ? <button type="button" className="worker-outline-button" disabled={busy || replay} onClick={() => void doConsent()}>{busy ? "…" : t.grant}</button> : <button type="button" className="worker-outline-button worker-revoke" disabled={busy} onClick={() => void doConsent(true)}>{busy ? "…" : t.revoke}</button>}
            </div>}
            {!authConfigured && <p className="worker-demo-note">{t.localConsent}</p>}
          </section>
        </> : <section className="worker-ack"><span className="label">05 / YOUR CHOICE</span><div className="worker-ack-symbol" aria-hidden="true">P</div><h2>{lang === "hi" ? "आपके नियंत्रण में" : "Your choice"}</h2><p>{lang === "hi" ? "पर्ची खुलने के बाद ही अपनी पुष्टि या सहायता-अनुमति पर निर्णय लें।" : "Review your own Parchi before deciding whether to acknowledge it or allow assistance."}</p></section>}</aside>
      </div>
      <footer className="worker-footer">{t.legal}{view && <details><summary>{t.refs}</summary><code>{view.site_id} · {view.parchi_id}{view.expires_at ? ` · expires ${formatInstant(view.expires_at)}` : ""}</code></details>}</footer>
  </main>;
}

function LanguageToggle({ lang, setLang }: { lang: Lang; setLang: (lang: Lang) => void }) {
  return <div className="worker-language" role="group" aria-label="Language"><button type="button" aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>हिन्दी</button><button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button></div>;
}
function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
