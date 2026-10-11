"use client";

import Link from "next/link";
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import type { PublicImpactPayload, VerifyPayload } from "@/lib/types";
import { DEMO_OFFICIAL_STAGE, DEMO_READING, DEMO_VERIFY_PAYLOAD } from "@/lib/demo-seed";

const LandingScene = lazy(() => import("@/components/SiteSceneExplorer").then((module) => ({ default: module.SiteSceneExplorer })));

const ACTIVITIES = [
  { name: "Demolition", detail: "Illustrative scenario · no activity result returned", status: "UNKNOWN", icon: "demolition" },
  { name: "Piling works", detail: "Illustrative scenario · no activity result returned", status: "UNKNOWN", icon: "piling" },
  { name: "Material transport", detail: "Illustrative scenario · no activity result returned", status: "UNKNOWN", icon: "truck" },
  { name: "C&D waste management", detail: "Illustrative scenario · no activity result returned", status: "UNKNOWN", icon: "recycle" },
];

const FLOW = [
  { title: "Official order", caption: "A CAQM invocation enters the record.", href: "/verify", icon: "source" },
  { title: "Source verified", caption: "Source bytes and cited clauses are checked.", href: "/verify", icon: "check" },
  { title: "Obligations resolved", caption: "The deterministic resolver applies site facts.", href: "/supervisor", icon: "rules" },
  { title: "Action authorized", caption: "Cedar checks who may act at this site.", href: "/cedar", icon: "shield" },
  { title: "Worker informed", caption: "A Parchi carries the reason and its evidence.", href: "/worker", icon: "worker" },
  { title: "Acknowledgement sealed", caption: "The worker confirms; the record is sealed.", href: "/worker", icon: "lock" },
];

const GLYPHS: Record<string, string> = {
  demolition: "M4 18 13.5 4 22 18H4Zm5-1h7m-3.5-8v4m-3.5 1 7 3",
  piling: "M6 3v18m6-18v18m6-18v18M3 8h18M3 15h18m-9-4v2",
  truck: "M3 7h11v10H3zM14 10h4l3 3v4h-7zM7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  recycle: "m8 4 3-2 3 2-2 3M5 8l-3 5 3 2m12-7 4 2-1 4h-3m-8 5 1 3 5 1 2-3m-8-8 4 2 2-3m5 5-4-2-2 3",
  source: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 3h7m-7 3h5",
  check: "m5 12 4 4L19 6M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z",
  rules: "M4 5h16M4 12h16M4 19h16M8 3v4m8 3v4m-5 3v4",
  shield: "M12 3 20 6v5c0 5-3.4 8-8 10-4.6-2-8-5-8-10V6l8-3Zm-4 9 3 3 5-6",
  worker: "M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-7 9c0-4 2.5-6 7-6s7 2 7 6M4 4v2m16-2v2M3 2h18v6H3z",
  lock: "M5 10h14v11H5zM8 10V7a4 4 0 1 1 8 0v3m-4 4v3",
};

function Mark({ kind }: { kind: string }) {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d={GLYPHS[kind] ?? GLYPHS.source} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

const NODES = [
  {
    title: "CAQM source",
    short: "01 / SOURCE",
    role: "The corpus contains official CAQM GRAP PDFs and their recorded source URLs.",
    input: "Documents published by CAQM.",
    output: "Versioned source records and extracted page text.",
    guarantee: "The manifest binds each document to its SHA-256 digest.",
    status: "3 source PDFs in the repository",
  },
  {
    title: "Citation verification",
    short: "02 / PROOF",
    role: "The verifier re-proves source bytes and quotations against indexed pages.",
    input: "Manifest, PDF bytes, cited pages and exact quotations.",
    output: "Pass or fail details from the real corpus verifier.",
    guarantee: "A citation only counts after the source hash and quotation match.",
    status: "Implemented · run the verifier below",
  },
  {
    title: "Obligation resolver",
    short: "03 / RULES",
    role: "Pure deterministic code combines verified rules, an official invocation and site facts.",
    input: "Verified corpus, site facts and the official invocation.",
    output: "MET, NOT_MET, UNKNOWN or NOT_APPLICABLE results with citations.",
    guarantee: "An AQI observation by itself does not activate a legal workflow.",
    status: "Implemented · available in the supervisor workspace",
  },
  {
    title: "Cedar authorization",
    short: "04 / AUTHORITY",
    role: "In-process Cedar policies decide whether a principal may take an action.",
    input: "Principal, requested action and the resource.",
    output: "An allow or a denial with a policy explanation.",
    guarantee: "Authorization does not decide legal obligations or replace workflow rules.",
    status: "Implemented · local Cedar 4.x policy",
  },
  {
    title: "Standing Order",
    short: "05 / COMMITMENT",
    role: "A supervisor can create a time-bounded commitment for one site and a supported trigger.",
    input: "Authorized supervisor, one site, trigger, actions and validity window.",
    output: "A confirmed order and the local demonstration workflow.",
    guarantee: "The order accepts no arbitrary code or open-ended agent instructions.",
    status: "Local workflow implemented · AWS deployment is not live",
  },
  {
    title: "Worker Parchi",
    short: "06 / PARCHI",
    role: "The workflow creates a site-specific Parchi with the restriction and its provenance.",
    input: "Resolved obligation, official-stage record and roster entry.",
    output: "A pending acknowledgement and a token-only QR link.",
    guarantee: "The QR token contains no worker identity or Parchi details.",
    status: "Implemented · local demonstration workflow",
  },
  {
    title: "Worker acknowledgement",
    short: "07 / CONFIRM",
    role: "The named worker acknowledges their own Parchi through the authorization boundary.",
    input: "Single-use acknowledgement token and worker identity.",
    output: "An acknowledgement event and sealed record state.",
    guarantee: "Supervisors cannot acknowledge for a worker; duplicate taps are idempotent.",
    status: "Implemented · worker flow and Cedar boundary",
  },
  {
    title: "Evidence record",
    short: "08 / RECORD",
    role: "The audit chain keeps the source, decision and worker acknowledgement connected.",
    input: "Verified source, obligation result, authorization and workflow events.",
    output: "A sealed Parchi content hash and audit events.",
    guarantee: "A pending Parchi cannot be sealed before the worker acknowledges it.",
    status: "Domain lifecycle implemented · stores are in memory locally",
  },
];

const PROVENANCE = [
  { label: "RULE", detail: "A resolver obligation keeps its rule identifier and citation. The supervisor workspace shows the actual site result and the clause that supports it.", link: "/supervisor" },
  { label: "PAGE", detail: "Every citation identifies the page that the quoted text was extracted from.", link: "/verify" },
  { label: "EXACT QUOTE", detail: "The verifier checks that the recorded quotation appears verbatim in the indexed page text.", link: "/verify" },
  { label: "EXTRACTED TEXT", detail: "Page text is treated as a citation index; by itself it does not establish that the source PDF is authentic.", link: "/verify" },
  { label: "ORIGINAL PDF", detail: "The corpus currently records three official CAQM source PDFs.", link: "/verify" },
  { label: "SHA-256", detail: "The verifier re-computes source-file digests and compares them with the corpus manifest.", link: "/verify" },
  { label: "CAQM SOURCE", detail: "The source manifest retains the official CAQM source URL for each verified document.", link: "/verify" },
];

type Health = { status: string };

const DEMO_PUBLIC_IMPACT: PublicImpactPayload = {
  mode: "REPLAY",
  is_replay: true,
  is_current_invocation: false,
  invocation: {
    stage: DEMO_OFFICIAL_STAGE.stage,
    invoked_at: DEMO_OFFICIAL_STAGE.invoked_at,
    order_doc_id: DEMO_OFFICIAL_STAGE.order_doc_id,
    order_sha256: DEMO_OFFICIAL_STAGE.citation.source_hash,
    lifecycle: "revoked",
    revoked_at: DEMO_OFFICIAL_STAGE.revoked_at,
    is_current: false,
    describe: "Stage III was invoked on 16 January 2026 and revoked on 22 January 2026. This cited record is historical and is not in force.",
  },
  reading: {
    station_id: DEMO_READING.station_id,
    parameter: DEMO_READING.parameter,
    value: DEMO_READING.value,
    observed_at: DEMO_READING.observed_at,
    provenance: "synthetic",
    is_synthetic: true,
    is_measured: false,
    is_replay: false,
  },
  metrics: {
    sites_with_active_standing_orders: { count: 0, label: "Active Standing Orders", description: "No current live status is seeded.", status: "unavailable", status_reason: "Historical replay demo", reporting_period: null },
    sites_acknowledging_regulated_halts: { count: 0, label: "Sites acknowledging halts", description: "No current live status is seeded.", status: "unavailable", status_reason: "Historical replay demo", reporting_period: null },
    dust_activities_halted: { count: 0, label: "Dust activities halted", description: "No current live status is seeded.", status: "unavailable", status_reason: "Historical replay demo", reporting_period: null },
    workers_with_documented_displacement: { count: 0, label: "Workers with documented displacement", description: "No current live status is seeded.", status: "unavailable", status_reason: "Historical replay demo", reporting_period: null },
  },
  data_note: "The demo uses a cited historical invocation and a synthetic reading example. It has no live site status.",
  claim_boundary: "The record demonstrates provenance and workflow; it does not establish current restrictions or entitlement.",
};

function SiteIllustration({ active }: { active: number }) {
  return (
    <div className="site-visual" aria-label="Interactive diagram of an environmental restriction flowing through a construction site" role="img">
      <div className="site-visual-top"><span>SCHEMATIC / SITE FLOW</span><span>ILLUSTRATIVE CONSTRUCTION SITE</span></div>
      <svg className="site-svg" viewBox="0 0 760 490" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="platform" x1="110" y1="250" x2="650" y2="445" gradientUnits="userSpaceOnUse"><stop stopColor="#e6eef6"/><stop offset="1" stopColor="#cddbe9"/></linearGradient>
          <linearGradient id="tower" x1="314" y1="111" x2="438" y2="346" gradientUnits="userSpaceOnUse"><stop stopColor="#c8d7e3"/><stop offset="1" stopColor="#9fb2c2"/></linearGradient>
          <linearGradient id="path" x1="91" y1="287" x2="658" y2="320" gradientUnits="userSpaceOnUse"><stop stopColor="#1769e8"/><stop offset="1" stopColor="#7da9ed"/></linearGradient>
          <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" stroke="#7189a5" strokeOpacity=".16"/></pattern>
          <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <path d="m81 327 265-163 329 137-274 160L81 327Z" fill="url(#platform)" stroke="#9bb0c4" strokeWidth="1.2"/>
        <path d="m104 325 241-147 291 123-245 142-287-118Z" fill="url(#grid)" stroke="#8da3b8" strokeOpacity=".4"/>
        <path d="m310 342 0-202 80-46 84 34v193l-82 49-82-28Z" fill="url(#tower)" stroke="#8298ad" strokeOpacity=".7"/>
        <path d="m390 94 0 203 84-41V128l-84-34Z" fill="#aebfcd" stroke="#8298ad" strokeOpacity=".65"/>
        <path d="m310 140 80 42 84-43M310 190l80 41 84-43M310 241l80 42 84-44M310 291l81 39 83-43" stroke="#6f879d" strokeOpacity=".45"/>
        <path d="M274 133h160M333 130V74m-53 0h110m-74 0-30 55m61-55 34 55" stroke="#73889c" strokeOpacity=".85" strokeWidth="3"/>
        <path d="M380 74V39m-2 0 97 14" stroke="#73889c" strokeOpacity=".85" strokeWidth="2"/>
        <path d="m514 316 48-28 45 19-48 29-45-20Z" fill="#d7e1e8" stroke="#8197aa" strokeOpacity=".65"/>
        <path d="m532 310 14-9 12 6m-7 19 24-14" stroke="#b0beb1" strokeOpacity=".6" strokeWidth="2"/>
        <path d="m208 286 33-20 44 19-34 21-43-20Z" fill="#c4d3dc" stroke="#1769e8" strokeOpacity=".6"/>
        <path d="m229 285 12 14m-1-18 14 13m-2-16 15 13" stroke="#d8ebc4" strokeWidth="1.5"/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="#fff" strokeWidth="15" strokeLinecap="round"/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="url(#path)" strokeWidth="3" strokeLinecap="round" filter="url(#glow)" opacity={active >= 1 ? .96 : .55}/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="url(#path)" strokeWidth="2" strokeLinecap="round" strokeDasharray="5 10" className="path-flow"/>
        <g className={active === 0 || active === 1 ? "scene-point is-active" : "scene-point"}>
          <circle cx="88" cy="287" r="20" fill="#fff" stroke="#1769e8" strokeWidth="1.5"/><path d="M81 278h14v18H81zM84 282h8m-8 4h8m-8 4h6" stroke="#526985" strokeWidth="1.4"/>
        </g>
        <g className={active === 2 || active === 3 ? "scene-point is-active" : "scene-point"}>
          <circle cx="399" cy="280" r="23" fill="#fff" stroke="#1769e8" strokeWidth="1.5"/><path d="M399 269v12m0 6h.01" stroke="#526985" strokeWidth="2" strokeLinecap="round"/>
        </g>
        <g className={active >= 4 ? "scene-point is-active" : "scene-point"}>
          <circle cx="669" cy="329" r="20" fill="#fff" stroke="#1769e8" strokeWidth="1.5"/><path d="m661 329 5 5 10-11" stroke="#21834d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </g>
        <path d="M142 360h82m198 56h103" stroke="#8196aa" strokeOpacity=".55" strokeDasharray="3 7"/>
        <circle cx="239" cy="216" r="2" fill="#c7fb56"/><circle cx="274" cy="232" r="1.5" fill="#a8e4b3"/><circle cx="541" cy="197" r="1.5" fill="#a8e4b3"/><circle cx="576" cy="207" r="2" fill="#c7fb56"/>
        <text x="52" y="250" fill="#526985" fontSize="10" letterSpacing="1.3">ORDER</text><text x="351" y="237" fill="#526985" fontSize="10" letterSpacing="1.3">SITE ACTION</text><text x="623" y="370" fill="#526985" fontSize="10" letterSpacing="1.3">WORKER</text>
      </svg>
      <div className="site-visual-foot"><span><i className="status-dot"/> SYSTEM MAP · NOT A LIVE SITE FEED</span><span>01 — 06</span></div>
    </div>
  );
}

export function ExperienceHome() {
  const [demoMode, setDemoMode] = useState(process.env.NEXT_PUBLIC_AADESH_DEMO === "1");
  const [flowStep, setFlowStep] = useState(0);
  const [nodeIndex, setNodeIndex] = useState(0);
  const [mode, setMode] = useState<"CURRENT" | "REPLAY">(process.env.NEXT_PUBLIC_AADESH_DEMO === "1" ? "REPLAY" : "CURRENT");
  const [impact, setImpact] = useState<PublicImpactPayload | null>(process.env.NEXT_PUBLIC_AADESH_DEMO === "1" ? DEMO_PUBLIC_IMPACT : null);
  const [verify, setVerify] = useState<VerifyPayload | null>(process.env.NEXT_PUBLIC_AADESH_DEMO === "1" ? DEMO_VERIFY_PAYLOAD : null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [provenanceIndex, setProvenanceIndex] = useState(5);
  const [activityIndex, setActivityIndex] = useState(0);
  const activeNode = NODES[nodeIndex];
  const proofSummary = useMemo(() => {
    const output = verify?.verify.output ?? "";
    const sources = output.match(/manifest entries\s*:\s*(\d+)/)?.[1];
    const citations = output.match(/entries checked\s*:\s*(\d+)/)?.[1];
    return { sources, citations };
  }, [verify]);

  useEffect(() => {
    const demo = process.env.NEXT_PUBLIC_AADESH_DEMO === "1" ||
      new URLSearchParams(window.location.search).get("demo") === "1" ||
      window.sessionStorage.getItem("aadesh_demo") === "1";
    setDemoMode(demo);
    if (demo) {
      setMode("REPLAY");
      setImpact(DEMO_PUBLIC_IMPACT);
      setVerify(DEMO_VERIFY_PAYLOAD);
    }
  }, []);

  useEffect(() => {
    if (demoMode) return;
    let alive = true;
    Promise.allSettled([
      getJson<PublicImpactPayload>("/api/impact"),
      getJson<VerifyPayload>("/api/verify"),
      getJson<Health>("/api/health"),
    ]).then(([impactResult, verifyResult, healthResult]) => {
      if (!alive) return;
      setImpact(impactResult.status === "fulfilled" ? impactResult.value : null);
      setVerify(verifyResult.status === "fulfilled" ? verifyResult.value : null);
      setApiOnline(healthResult.status === "fulfilled" && healthResult.value.status === "ok");
    });
    return () => { alive = false; };
  }, [demoMode]);

  const invocation = impact?.invocation;
  const shownStage = mode === "CURRENT" ? (impact?.is_current_invocation ? `Stage ${invocation?.stage}` : "No active invocation") : invocation ? `Stage ${invocation.stage} · historical` : "No replay record";
  const observationOrigin = !impact?.reading
    ? "NO PUBLIC READING"
    : mode === "REPLAY" && !impact.reading.is_replay
      ? "SYNTHETIC EXAMPLE · NOT REPLAY DATA"
      : impact.reading.is_measured
        ? "MEASURED"
        : impact.reading.is_synthetic
          ? "SYNTHETIC EXAMPLE"
          : impact.reading.is_replay
            ? "HISTORICAL REPLAY INPUT"
            : impact.reading.provenance;

  return (
    <div className="experience-home">
      <header className="landing-header">
        <Link href="/" className="landing-brand" aria-label="Aadesh home"><span className="landing-leaf" aria-hidden="true"><svg viewBox="0 0 28 28" fill="none"><path d="M21.5 3.5C12.2 4.1 6.7 8.3 6.7 15.1c0 4.4 3.2 7.4 7.2 7.4 6.8 0 8.7-9.3 7.6-19Z" fill="currentColor"/><path d="M7.2 23.5c2.1-4.1 5.3-7.6 10.2-11.1" stroke="#07100f" strokeWidth="1.5" strokeLinecap="round"/></svg></span><strong>Aadesh</strong><span>Clean air. Compliant sites. Protected workers.</span></Link>
        <nav aria-label="Landing page navigation"><a href="#how-it-works">How it works</a><a href="#evidence">Evidence</a><a href="#worker-protection">Worker protection</a><a href="#architecture">Technology</a></nav>
        <Link className="landing-nav-cta" href="/supervisor?demo=1">Explore demo <span aria-hidden="true">→</span></Link>
      </header>
      <section className="experience-hero" id="product">
        <div className="hero-copy">
          <div className="hero-titlemark"><span className="hero-product-label">AN ENVIRONMENTAL COMPLIANCE EXECUTION SYSTEM</span></div>
          <h1>Make compliance <em>executable.</em></h1>
          <p className="hero-lede">Turn official pollution-control orders into site actions, cited evidence and worker acknowledgement.</p>
          <div className="hero-actions"><a href="#interactive-demo" className="action-primary">Explore interactive demo <span aria-hidden="true">→</span></a><Link href="/verify" className="action-secondary">View source verification</Link></div>
          <div className="hero-proof-points"><span><b aria-hidden="true">▤</b><strong>Real CAQM sources</strong><small>with page-level citations</small></span><span><b aria-hidden="true">⬡</b><strong>Deterministic rules</strong><small>no AI legal decisions</small></span><span><b aria-hidden="true">▦</b><strong>Worker Parchis</strong><small>verifiable records</small></span></div>
          <div className="hero-status"><span className={demoMode || apiOnline ? "status-dot" : "status-dot is-muted"}/><span>{demoMode ? "Seeded demonstration · no API required" : apiOnline === null ? "Checking local system" : apiOnline ? "Local demonstration API responding" : "Local API unavailable"}</span><span className="status-separator">·</span><span>{impact ? mode === "REPLAY" ? "REVOKED REPLAY · NOT CURRENT" : impact.is_current_invocation ? `CURRENT OFFICIAL STAGE ${impact.invocation?.stage ?? ""}` : "NO CURRENT OFFICIAL INVOCATION" : apiOnline === false ? "OFFICIAL STATUS UNAVAILABLE" : "CHECKING OFFICIAL RECORD"}</span></div>
        </div>
        <div className="landing-hero-visual" id="interactive-demo">
          <div className="landing-scene-heading"><span>ILLUSTRATIVE CONSTRUCTION SITE</span><span className="scene-live-label"><i/> NOT A LIVE SITE FEED</span></div>
          <Suspense fallback={<SiteIllustration active={flowStep}/> }><LandingScene title="Explore the site model" label="3D SITE MODEL" landing activityIndex={activityIndex} /></Suspense>
          <div className="landing-activity-panel"><div className="activity-panel-heading"><span>HISTORICAL REPLAY</span><span className="scenario-info" title="This is a historical demonstration. No active invocation is represented." aria-label="Historical demonstration only">i</span></div><strong>GRAP Stage III <small>· Jan 2026</small></strong><b className="revoked-label">Revoked · 22 Jan 2026</b><div className="activity-citation"><span className="citation-file"><Mark kind="source" /> CAQM source · page 1</span><span className="citation-hash">SHA-256 {DEMO_OFFICIAL_STAGE.citation.source_hash.slice(0, 8)}…</span></div><div className="activity-list-label">Choose a site activity</div><div className="activity-list" role="group" aria-label="Select illustrative activity">{ACTIVITIES.map((activity, index) => <button key={activity.name} type="button" aria-pressed={activityIndex === index} onClick={() => setActivityIndex(index)}><Mark kind={activity.icon}/><span>{activity.name}</span><span className="activity-chevron" aria-hidden="true">›</span></button>)}</div><div className="activity-result" aria-live="polite"><span className="unknown-badge">{ACTIVITIES[activityIndex].status}</span><p>{ACTIVITIES[activityIndex].detail}. <Link href="/verify">Source</Link> · <Link href="/supervisor?demo=1">Next step</Link></p></div></div>
          <div className="scene-source-chip">Official CAQM source · page 1 · <Link href="/verify">inspect citation ↗</Link></div>
        </div>
        <div className="hero-bottomline"><span>01 / HOW THE RECORD MOVES</span><span>SELECT A STEP TO FOLLOW THE EVIDENCE</span></div>
      </section>

      <section className="experience-section flow-section" id="how-it-works">
        <div className="section-intro"><span className="section-index">01 — THE FLOW</span><h2>One decision.<br/><em>A traceable path.</em></h2><p>Follow a restriction from its official source to the worker who acknowledges it.</p></div>
        <div className="flow-explorer">
          <div className="flow-rail" role="tablist" aria-label="Environmental compliance workflow">
            {FLOW.map((step, index) => <button type="button" role="tab" aria-selected={flowStep === index} className={`flow-step ${flowStep === index ? "is-selected" : ""} ${index < flowStep ? "is-past" : ""}`} key={step.title} onClick={() => setFlowStep(index)}><span className="flow-step-number">0{index + 1}</span><span className="flow-step-icon"><Mark kind={step.icon}/></span><span className="flow-step-title">{step.title}</span><span className="flow-step-node" aria-hidden="true"/></button>)}
          </div>
          <div className="flow-readout" aria-live="polite"><span className="section-index">STEP 0{flowStep + 1} / 06</span><h3>{FLOW[flowStep].title}</h3><p>{FLOW[flowStep].caption}</p><Link href={FLOW[flowStep].href}>Explore this part <span aria-hidden="true">↗</span></Link></div>
        </div>
      </section>

      <section className="experience-section system-section" id="system-map">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">02 — SYSTEM MAP</span><h2>Follow the <em>authority.</em></h2><p>Enforcement is deterministic. Explanations branch off after the result.</p></div><div className="path-key"><span><i className="key-line"/>ENFORCEMENT PATH</span><span><i className="key-dash"/>OPTIONAL EXPLANATION</span></div></div>
        <div className="system-map">
          <svg className="system-connectors" viewBox="0 0 1000 200" preserveAspectRatio="none" aria-hidden="true"><path d="M60 74H940"/><path className="optional-connector" d="M405 78v70h174v-70"/></svg>
          <div className="system-nodes" role="tablist" aria-label="System components">
            {NODES.map((node, index) => <button key={node.title} type="button" role="tab" aria-selected={nodeIndex === index} className={`system-node ${nodeIndex === index ? "is-selected" : ""}`} onClick={() => setNodeIndex(index)}><span className="system-node-number">{String(index + 1).padStart(2, "0")}</span><span className="system-node-icon"><Mark kind={(["source", "check", "rules", "shield", "lock", "worker", "check", "lock"] as const)[index]}/></span><span className="system-node-name">{node.title}</span></button>)}
          </div>
          <button className="explanation-branch" type="button" aria-expanded={explanationOpen} onClick={() => setExplanationOpen((open) => !open)}><span>OPTIONAL · READ ONLY</span><b>Plain-language explanation</b><small>Follows a computed result · never authorizes</small></button>
          {explanationOpen && <div className="explanation-inspector" aria-live="polite"><span className="section-index">PRESENTATION ONLY · NOT AN AUTHORITY</span><strong>The deterministic result remains the source of truth.</strong><p>The codebase includes a deterministic explanation fallback and optional model adapter. The local HTTP API does not expose an explanation endpoint, so no model-generated explanation is presented here.</p><Link href="/supervisor">Inspect a cited resolver result <span aria-hidden="true">↗</span></Link></div>}
          <div className="node-inspector" aria-live="polite"><div className="inspector-title"><span className="section-index">{activeNode.short}</span><span className="implementation-status"><i className="status-dot"/>{activeNode.status}</span></div><h3>{activeNode.title}</h3><p className="node-role">{activeNode.role}</p><dl className="node-facts"><div><dt>IN</dt><dd>{activeNode.input}</dd></div><div><dt>OUT</dt><dd>{activeNode.output}</dd></div><div><dt>BOUNDARY</dt><dd>{activeNode.guarantee}</dd></div></dl></div>
          <p className="map-footnote">Step Functions, AWS hosting and persistent cloud stores are documented architecture, not deployed services.</p>
        </div>
      </section>

      <section className="experience-section stage-section" id="stage-explorer">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">03 — GRAP STATUS</span><h2>An observation can suggest.<br/><em>An order activates.</em></h2><p>AQ measurements, implied stages and official invocations are separate facts.</p></div><Link className="text-link" href="/supervisor">Open obligation workspace <span aria-hidden="true">↗</span></Link></div>
        <div className="stage-explorer">
          <div className="stage-controls" role="group" aria-label="Select official stage record"><button type="button" aria-pressed={mode === "CURRENT"} className={mode === "CURRENT" ? "is-selected" : ""} onClick={() => setMode("CURRENT")}>Current record</button><button type="button" aria-pressed={mode === "REPLAY"} className={mode === "REPLAY" ? "is-selected" : ""} onClick={() => setMode("REPLAY")}>Historical replay</button></div>
          <div className="stage-display" aria-live="polite"><div className="stage-main"><span className="section-index">OFFICIAL CAQM RECORD · {mode}</span><div className="stage-value">{impact ? shownStage : apiOnline === false ? "Status unavailable" : "Loading record…"}</div><p>{mode === "CURRENT" ? apiOnline === false ? "The public status API did not respond. No current status is being inferred." : impact?.is_current_invocation ? "An official invocation is recorded as active." : "The bundled corpus has no current official invocation. No restriction is activated by this interface." : invocation ? invocation.describe : apiOnline === false ? "The public status API did not respond, so the historical record could not be loaded." : "No historical invocation appears in the public record."}</p></div><div className="stage-measure"><span className="section-index">ENVIRONMENTAL OBSERVATION</span>{impact?.reading ? <><strong>{impact.reading.value} <small>{impact.reading.parameter}</small></strong><span className="observation-origin">{observationOrigin}</span></> : <><strong>—</strong><span className="observation-origin">{apiOnline === false ? "UNAVAILABLE · API OFFLINE" : observationOrigin}</span></>}<p>A measurement does not, on its own, activate a compliance workflow.</p></div><div className="stage-implied"><span className="section-index">STAGE IMPLIED BY READING</span><strong>Not available</strong><span className="observation-origin">NOT IN PUBLIC RECORD</span><p>Use a supported observation profile in the supervisor workspace to inspect the comparison.</p></div></div>
          <div className={`replay-caveat ${mode === "REPLAY" ? "is-visible" : ""}`}><span>!</span><p>Historical replay only. The recorded Stage III invocation was revoked on 22 January 2026. Its replay is not a current restriction or proof of historical site obligations.</p></div>
          {apiOnline === false && <p className="inline-note">The public status API is unavailable. Start the backend with <code>make api</code> to load recorded status.</p>}
        </div>
      </section>

      <section className="experience-section evidence-section" id="evidence">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">04 — PROVENANCE</span><h2>Evidence you can <em>inspect.</em></h2><p>Each decision can lead back through its citation to the bytes of an official source.</p></div><Link className="text-link" href="/verify">Open verification lab <span aria-hidden="true">↗</span></Link></div>
        <div className="evidence-trail" role="group" aria-label="Evidence provenance chain">{PROVENANCE.map((step, index) => <span className="provenance-step" key={step.label}><button type="button" aria-pressed={provenanceIndex === index} onClick={() => setProvenanceIndex(index)}>{step.label}</button>{index < PROVENANCE.length - 1 && <i aria-hidden="true">→</i>}</span>)}</div>
        <div className="provenance-inspector" aria-live="polite"><div><span className="section-index">{PROVENANCE[provenanceIndex].label} / EVIDENCE LINK</span><p>{PROVENANCE[provenanceIndex].detail}</p></div><Link href={PROVENANCE[provenanceIndex].link}>Inspect source record <span aria-hidden="true">↗</span></Link></div>
        <div className="evidence-console"><div className="evidence-verdict"><span className={verify?.verify.passed ? "verdict-mark is-good" : verify ? "verdict-mark is-bad" : "verdict-mark"}>{verify ? (verify.verify.passed ? "✓" : "!") : "···"}</span><div><span className="section-index">{demoMode ? "RECORDED LOCAL VERIFIER" : "LIVE LOCAL VERIFIER"}</span><strong>{verify ? (verify.verify.passed ? "Source integrity verified" : "Verification failed") : "Waiting for verifier"}</strong><span className="verdict-sub">{verify?.verify.command ?? "make verify"}</span></div></div><div className="evidence-counts"><div><strong>{proofSummary.sources ?? "—"}</strong><span>SOURCE FILES</span></div><div><strong>{proofSummary.citations ?? "—"}</strong><span>CITATIONS CHECKED</span></div></div><button type="button" className="evidence-expand" aria-expanded={sourceOpen} onClick={() => setSourceOpen((open) => !open)}>{sourceOpen ? "Hide verification output" : "Inspect verification output"}<span aria-hidden="true">{sourceOpen ? "−" : "+"}</span></button></div>
        {/* The verifier route needs a session, so a signed-out visitor gets no output from a
            perfectly healthy API. Blame the backend only when health actually failed. */}
        {sourceOpen && <pre className="verification-output">{verify?.verify.output ?? (apiOnline === false ? "The verifier output is not available. Start the API with make api." : "Sign in to run the verifier against the deployed corpus.")}</pre>}
        {verify?.tamper && <p className="tamper-note">Tamper check: <strong>{verify.tamper.caught ? "the isolated tamper was detected" : "not detected"}</strong>. This is the recorded output of the real scratch-copy check.</p>}
      </section>        <section className="experience-section journeys-section" id="worker-protection">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">05 — PEOPLE & OPERATIONS</span><h2>Two experiences.<br/><em>One accountable record.</em></h2><p>The site supervisor and the worker need different tools and different language.</p></div></div>
        <div className="journey-lines">
          <Link href="/site" className="journey-link supervisor-journey"><span className="section-index">SITE OPERATIONS / SUPERVISOR</span><strong>Understand the restriction.<br/>Commit to the action.</strong><span className="journey-foot">Obligations · cited clauses · Standing Order preview <b aria-hidden="true">↗</b></span></Link>
          <Link href="/worker" className="journey-link worker-journey"><span className="section-index">PERSONAL RECORD / WORKER</span><strong>Know why work stopped.<br/>Confirm for yourself.</strong><span className="journey-foot">Mobile Parchi · Hindi & English · own acknowledgement <b aria-hidden="true">↗</b></span></Link>
          <Link href="/facilitator" className="journey-link facilitator-journey"><span className="section-index">ASSISTANCE / FACILITATOR</span><strong>Help with a claim.<br/>Without the full record.</strong><span className="journey-foot">Consent-limited, redacted assistance <b aria-hidden="true">↗</b></span></Link>
        </div>
        <div className="boundaries-row"><Link href="/cedar">Authorization lab <span>Real Cedar decisions ↗</span></Link><Link href="/verify">Verification lab <span>Source integrity ↗</span></Link><Link href="/impact">Public impact <span>Aggregate data ↗</span></Link></div>
      </section>

      <section className="experience-section trust-section" id="trust">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">06 — WORKER PROTECTION & TRUST</span><h2>A worker’s own <em>evidence record.</em></h2><p>A Parchi documents the cited restriction and the worker’s acknowledgement. It is not a payment, claim, or guaranteed entitlement.</p></div></div>
        <div className="trust-grid">
          <article className="trust-card parchi-preview"><span className="section-index">WORKER PARCHI · SEEDED DEMO</span><div className="phone-frame"><div className="phone-topline">9:41 <span>●●●</span></div><strong>Aadesh <small>Worker Parchi</small></strong><span className="parchi-status">Work stopped · historical replay</span><p>Reason: cited Stage III restriction</p><p>Source: CAQM order · open page citation</p><p>Preparation: keep work records for official review. No entitlement or amount determined.</p><div className="qr-placeholder" aria-hidden="true">▦</div><span className="parchi-button">Acknowledgement demo</span></div><p className="trust-footnote">Fictional interface preview. No worker identity or QR token is shown.</p><Link href="/worker?demo=1">Open seeded worker experience ↗</Link></article>
          <article className="trust-card authorization-card"><span className="section-index">IDENTITY & AUTHORIZATION</span><div className="authorization-visual" aria-hidden="true"><span className="identity-token"><Mark kind="worker"/><i>WORKER</i></span><span className="auth-gate"><Mark kind="shield"/><small>CEDAR</small></span><span className="identity-token identity-denied"><Mark kind="worker"/><i>PROXY</i></span><span className="auth-allow">✓ OWN RECORD</span><span className="auth-deny">× PROXY DENIED</span></div><h3>Only the worker confirms their own record.</h3><p>Cedar blocks supervisor proxy acknowledgement at the action boundary.</p><Link href="/cedar">Inspect the Cedar decision ↗</Link><small>Local demo identity · no live worker data</small></article>
          <article className="trust-card"><span className="section-index">PLAIN-LANGUAGE EXPLANATION</span><h3>AI can explain a result. It cannot decide it.</h3><p>Legal obligations come from verified source text and deterministic rules. The optional explanation layer cannot alter the result or grant permission.</p><p className="trust-boundary">Facilitators receive only information the worker explicitly consents to share, with identifying details redacted.</p><Link href="/facilitator?demo=1">Explore consent-limited assistance ↗</Link></article>
        </div>
      </section>

      <section className="experience-section architecture-section" id="architecture">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">07 — TECHNOLOGY</span><h2>Built for evidence.<br/><em>Designed for impact.</em></h2><p>The local demonstration uses real source verification and deterministic rules. Cloud resources shown in the architecture are declared or planned and are not represented as a live deployment.</p></div><Link className="text-link" href="/evidence">Open evidence record ↗</Link></div>
        <div className="architecture-strip"><span><b><Mark kind="source"/></b> CAQM source</span><i>→</i><span><b><Mark kind="check"/></b> Hash & citation check</span><i>→</i><span><b><Mark kind="rules"/></b> Deterministic resolver</span><i>→</i><span><b><Mark kind="shield"/></b> Cedar authorization</span><i>→</i><span><b><Mark kind="worker"/></b> Parchi acknowledgement</span></div>
        <p className="architecture-note">Implemented locally: verifier, obligation resolver, Cedar policies and demonstration workflow. AWS resources are described in the repository template; deployment state is not asserted here. <a href="https://github.com/dhaanish597/AADHESH" target="_blank" rel="noreferrer">Source repository ↗</a> · <Link href="/verify">Open source verification ↗</Link> · <a href="https://github.com/dhaanish597/AADHESH/blob/main/docs/obligation-engine.md" target="_blank" rel="noreferrer">Obligation engine documentation ↗</a> · <a href="https://github.com/dhaanish597/AADHESH/blob/main/docs/corpus-audit.md" target="_blank" rel="noreferrer">Corpus audit ↗</a></p>
      </section>

      <footer className="experience-footer"><span>AADHESH <i className="footer-mark"/></span><p>Environmental operations, grounded in verifiable evidence.</p><span>DEMONSTRATION DATA IS LABELLED · NOT LEGAL ADVICE · NO CLAIM FILING</span><a className="model-attribution" href="https://sketchfab.com/3d-models/city-pack-8-102eef4837d84cfd9dae03af7ebe751a" target="_blank" rel="noreferrer">City Pack 8 by Pasha · CC BY 4.0</a></footer>
    </div>
  );
}
