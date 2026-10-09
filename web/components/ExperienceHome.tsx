"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import type { PublicImpactPayload, VerifyPayload } from "@/lib/types";

const FLOW = [
  { title: "Official order", caption: "A CAQM invocation enters the record.", href: "/verify" },
  { title: "Source verified", caption: "Source bytes and cited clauses are checked.", href: "/verify" },
  { title: "Obligations resolved", caption: "The deterministic resolver applies site facts.", href: "/supervisor" },
  { title: "Action authorized", caption: "Cedar checks who may act at this site.", href: "/cedar" },
  { title: "Worker informed", caption: "A Parchi carries the reason and its evidence.", href: "/worker" },
  { title: "Acknowledgement sealed", caption: "The worker confirms; the record is sealed.", href: "/worker" },
];

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

function SiteIllustration({ active }: { active: number }) {
  return (
    <div className="site-visual" aria-label="Interactive diagram of an environmental restriction flowing through a construction site" role="img">
      <div className="site-visual-top"><span>SCHEMATIC / SITE FLOW</span><span>ILLUSTRATIVE CONSTRUCTION SITE</span></div>
      <svg className="site-svg" viewBox="0 0 760 490" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="platform" x1="110" y1="250" x2="650" y2="445" gradientUnits="userSpaceOnUse"><stop stopColor="#243a32"/><stop offset="1" stopColor="#111b19"/></linearGradient>
          <linearGradient id="tower" x1="314" y1="111" x2="438" y2="346" gradientUnits="userSpaceOnUse"><stop stopColor="#42574d"/><stop offset="1" stopColor="#1c2925"/></linearGradient>
          <linearGradient id="path" x1="91" y1="287" x2="658" y2="320" gradientUnits="userSpaceOnUse"><stop stopColor="#c7fb56"/><stop offset="1" stopColor="#6ebd7b"/></linearGradient>
          <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" stroke="#c3d8cc" strokeOpacity=".08"/></pattern>
          <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <path d="m81 327 265-163 329 137-274 160L81 327Z" fill="url(#platform)" stroke="#496057" strokeWidth="1.2"/>
        <path d="m104 325 241-147 291 123-245 142-287-118Z" fill="url(#grid)" stroke="#9db0a2" strokeOpacity=".22"/>
        <path d="m310 342 0-202 80-46 84 34v193l-82 49-82-28Z" fill="url(#tower)" stroke="#9eafa2" strokeOpacity=".7"/>
        <path d="m390 94 0 203 84-41V128l-84-34Z" fill="#253630" stroke="#a8b8aa" strokeOpacity=".45"/>
        <path d="m310 140 80 42 84-43M310 190l80 41 84-43M310 241l80 42 84-44M310 291l81 39 83-43" stroke="#93a99a" strokeOpacity=".32"/>
        <path d="M274 133h160M333 130V74m-53 0h110m-74 0-30 55m61-55 34 55" stroke="#c3d0c2" strokeOpacity=".68" strokeWidth="3"/>
        <path d="M380 74V39m-2 0 97 14" stroke="#c3d0c2" strokeOpacity=".68" strokeWidth="2"/>
        <path d="m514 316 48-28 45 19-48 29-45-20Z" fill="#35473e" stroke="#a8b8aa" strokeOpacity=".5"/>
        <path d="m532 310 14-9 12 6m-7 19 24-14" stroke="#b0beb1" strokeOpacity=".6" strokeWidth="2"/>
        <path d="m208 286 33-20 44 19-34 21-43-20Z" fill="#51614d" stroke="#c7fb56" strokeOpacity=".65"/>
        <path d="m229 285 12 14m-1-18 14 13m-2-16 15 13" stroke="#d8ebc4" strokeWidth="1.5"/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="#1b271f" strokeWidth="15" strokeLinecap="round"/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="url(#path)" strokeWidth="3" strokeLinecap="round" filter="url(#glow)" opacity={active >= 1 ? .96 : .55}/>
        <path d="M88 287h142l83 44 86-51 99 14 69 35h104" stroke="url(#path)" strokeWidth="2" strokeLinecap="round" strokeDasharray="5 10" className="path-flow"/>
        <g className={active === 0 || active === 1 ? "scene-point is-active" : "scene-point"}>
          <circle cx="88" cy="287" r="20" fill="#101916" stroke="#c7fb56" strokeWidth="1.5"/><path d="M81 278h14v18H81zM84 282h8m-8 4h8m-8 4h6" stroke="#e2f0d9" strokeWidth="1.4"/>
        </g>
        <g className={active === 2 || active === 3 ? "scene-point is-active" : "scene-point"}>
          <circle cx="399" cy="280" r="23" fill="#101916" stroke="#c7fb56" strokeWidth="1.5"/><path d="M399 269v12m0 6h.01" stroke="#e2f0d9" strokeWidth="2" strokeLinecap="round"/>
        </g>
        <g className={active >= 4 ? "scene-point is-active" : "scene-point"}>
          <circle cx="669" cy="329" r="20" fill="#101916" stroke="#c7fb56" strokeWidth="1.5"/><path d="m661 329 5 5 10-11" stroke="#e2f0d9" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </g>
        <path d="M142 360h82m198 56h103" stroke="#90a097" strokeOpacity=".35" strokeDasharray="3 7"/>
        <circle cx="239" cy="216" r="2" fill="#c7fb56"/><circle cx="274" cy="232" r="1.5" fill="#a8e4b3"/><circle cx="541" cy="197" r="1.5" fill="#a8e4b3"/><circle cx="576" cy="207" r="2" fill="#c7fb56"/>
        <text x="52" y="250" fill="#ced9ce" fontSize="10" letterSpacing="1.3">ORDER</text><text x="351" y="237" fill="#ced9ce" fontSize="10" letterSpacing="1.3">SITE ACTION</text><text x="623" y="370" fill="#ced9ce" fontSize="10" letterSpacing="1.3">WORKER</text>
      </svg>
      <div className="site-visual-foot"><span><i className="status-dot"/> SYSTEM MAP · NOT A LIVE SITE FEED</span><span>01 — 06</span></div>
    </div>
  );
}

export function ExperienceHome() {
  const [flowStep, setFlowStep] = useState(0);
  const [nodeIndex, setNodeIndex] = useState(0);
  const [mode, setMode] = useState<"CURRENT" | "REPLAY">("CURRENT");
  const [impact, setImpact] = useState<PublicImpactPayload | null>(null);
  const [verify, setVerify] = useState<VerifyPayload | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [provenanceIndex, setProvenanceIndex] = useState(5);
  const activeNode = NODES[nodeIndex];
  const proofSummary = useMemo(() => {
    const output = verify?.verify.output ?? "";
    const sources = output.match(/manifest entries\s*:\s*(\d+)/)?.[1];
    const citations = output.match(/entries checked\s*:\s*(\d+)/)?.[1];
    return { sources, citations };
  }, [verify]);

  useEffect(() => {
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
  }, []);

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
      <section className="experience-hero" id="product">
        <div className="hero-copy">
          <div className="hero-titlemark"><span className="brand-glyph" aria-hidden="true"><i/><i/><i/></span><span>AADHESH</span><span className="hero-divider"/><span className="hero-product-label">ENVIRONMENTAL OPERATIONS</span></div>
          <h1>From environmental order to <em>verified action.</em></h1>
          <p className="hero-lede">Official restrictions. Site-specific obligations. A worker’s own acknowledgement. One evidence trail connects every step.</p>
          <div className="hero-actions"><Link href="/supervisor" className="action-primary">Explore the system <span aria-hidden="true">↗</span></Link><a className="action-secondary" href="#evidence">See how verification works <span aria-hidden="true">↓</span></a></div>
          <div className="hero-status"><span className={apiOnline ? "status-dot" : "status-dot is-muted"}/><span>{apiOnline === null ? "Checking local system" : apiOnline ? "Local demonstration API responding" : "Local API unavailable"}</span><span className="status-separator">·</span><span>{impact ? impact.is_current_invocation ? `CURRENT OFFICIAL STAGE ${impact.invocation?.stage ?? ""}` : "NO CURRENT OFFICIAL INVOCATION" : "CHECKING OFFICIAL RECORD"}</span></div>
        </div>
        <SiteIllustration active={flowStep}/>
        <div className="hero-bottomline"><span>01 / HOW THE RECORD MOVES</span><span>SELECT A STEP TO FOLLOW THE EVIDENCE</span></div>
      </section>

      <section className="experience-section flow-section" id="how-it-works">
        <div className="section-intro"><span className="section-index">01 — THE FLOW</span><h2>One decision.<br/><em>A traceable path.</em></h2><p>Follow a restriction from its official source to the worker who acknowledges it.</p></div>
        <div className="flow-explorer">
          <div className="flow-rail" role="tablist" aria-label="Environmental compliance workflow">
            {FLOW.map((step, index) => <button type="button" role="tab" aria-selected={flowStep === index} className={`flow-step ${flowStep === index ? "is-selected" : ""} ${index < flowStep ? "is-past" : ""}`} key={step.title} onClick={() => setFlowStep(index)}><span className="flow-step-number">0{index + 1}</span><span className="flow-step-title">{step.title}</span><span className="flow-step-node" aria-hidden="true"/></button>)}
          </div>
          <div className="flow-readout" aria-live="polite"><span className="section-index">STEP 0{flowStep + 1} / 06</span><h3>{FLOW[flowStep].title}</h3><p>{FLOW[flowStep].caption}</p><Link href={FLOW[flowStep].href}>Explore this part <span aria-hidden="true">↗</span></Link></div>
        </div>
      </section>

      <section className="experience-section system-section" id="system-map">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">02 — SYSTEM MAP</span><h2>Follow the <em>authority.</em></h2><p>Enforcement is deterministic. Explanations branch off after the result.</p></div><div className="path-key"><span><i className="key-line"/>ENFORCEMENT PATH</span><span><i className="key-dash"/>OPTIONAL EXPLANATION</span></div></div>
        <div className="system-map">
          <svg className="system-connectors" viewBox="0 0 1000 200" preserveAspectRatio="none" aria-hidden="true"><path d="M60 74H940"/><path className="optional-connector" d="M405 78v70h174v-70"/></svg>
          <div className="system-nodes" role="tablist" aria-label="System components">
            {NODES.map((node, index) => <button key={node.title} type="button" role="tab" aria-selected={nodeIndex === index} className={`system-node ${nodeIndex === index ? "is-selected" : ""}`} onClick={() => setNodeIndex(index)}><span className="system-node-number">{String(index + 1).padStart(2, "0")}</span><span className="system-node-name">{node.title}</span></button>)}
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
          <div className="stage-display" aria-live="polite"><div className="stage-main"><span className="section-index">OFFICIAL CAQM RECORD · {mode}</span><div className="stage-value">{impact ? shownStage : "Loading record…"}</div><p>{mode === "CURRENT" ? (impact?.is_current_invocation ? "An official invocation is recorded as active." : "The bundled corpus has no current official invocation. No restriction is activated by this interface.") : invocation ? invocation.describe : "No historical invocation appears in the public record."}</p></div><div className="stage-measure"><span className="section-index">ENVIRONMENTAL OBSERVATION</span>{impact?.reading ? <><strong>{impact.reading.value} <small>{impact.reading.parameter}</small></strong><span className="observation-origin">{observationOrigin}</span></> : <><strong>—</strong><span className="observation-origin">{observationOrigin}</span></>}<p>A measurement does not, on its own, activate a compliance workflow.</p></div><div className="stage-implied"><span className="section-index">STAGE IMPLIED BY READING</span><strong>Not available</strong><span className="observation-origin">NOT IN PUBLIC RECORD</span><p>Use a supported observation profile in the supervisor workspace to inspect the comparison.</p></div></div>
          <div className={`replay-caveat ${mode === "REPLAY" ? "is-visible" : ""}`}><span>!</span><p>Historical replay only. The recorded Stage III invocation was revoked on 22 January 2026. Its replay is not a current restriction or proof of historical site obligations.</p></div>
          {apiOnline === false && <p className="inline-note">The public status API is unavailable. Start the backend with <code>make api</code> to load recorded status.</p>}
        </div>
      </section>

      <section className="experience-section evidence-section" id="evidence">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">04 — PROVENANCE</span><h2>Evidence you can <em>inspect.</em></h2><p>Each decision can lead back through its citation to the bytes of an official source.</p></div><Link className="text-link" href="/verify">Open verification lab <span aria-hidden="true">↗</span></Link></div>
        <div className="evidence-trail" role="group" aria-label="Evidence provenance chain">{PROVENANCE.map((step, index) => <span className="provenance-step" key={step.label}><button type="button" aria-pressed={provenanceIndex === index} onClick={() => setProvenanceIndex(index)}>{step.label}</button>{index < PROVENANCE.length - 1 && <i aria-hidden="true">→</i>}</span>)}</div>
        <div className="provenance-inspector" aria-live="polite"><div><span className="section-index">{PROVENANCE[provenanceIndex].label} / EVIDENCE LINK</span><p>{PROVENANCE[provenanceIndex].detail}</p></div><Link href={PROVENANCE[provenanceIndex].link}>Inspect source record <span aria-hidden="true">↗</span></Link></div>
        <div className="evidence-console"><div className="evidence-verdict"><span className={verify?.verify.passed ? "verdict-mark is-good" : verify ? "verdict-mark is-bad" : "verdict-mark"}>{verify ? (verify.verify.passed ? "✓" : "!") : "···"}</span><div><span className="section-index">LIVE LOCAL VERIFIER</span><strong>{verify ? (verify.verify.passed ? "Source integrity verified" : "Verification failed") : "Waiting for verifier"}</strong><span className="verdict-sub">{verify?.verify.command ?? "make verify"}</span></div></div><div className="evidence-counts"><div><strong>{proofSummary.sources ?? "—"}</strong><span>SOURCE FILES</span></div><div><strong>{proofSummary.citations ?? "—"}</strong><span>CITATIONS CHECKED</span></div></div><button type="button" className="evidence-expand" aria-expanded={sourceOpen} onClick={() => setSourceOpen((open) => !open)}>{sourceOpen ? "Hide verification output" : "Inspect verification output"}<span aria-hidden="true">{sourceOpen ? "−" : "+"}</span></button></div>
        {sourceOpen && <pre className="verification-output">{verify?.verify.output ?? "The verifier output is not available. Start the API with make api."}</pre>}
        {verify?.tamper && <p className="tamper-note">Tamper check: <strong>{verify.tamper.caught ? "the isolated tamper was detected" : "not detected"}</strong>. This is the recorded output of the real scratch-copy check.</p>}
      </section>

      <section className="experience-section journeys-section" id="journeys">
        <div className="section-heading-row"><div className="section-intro"><span className="section-index">05 — PEOPLE & OPERATIONS</span><h2>Two experiences.<br/><em>One accountable record.</em></h2><p>The site supervisor and the worker need different tools and different language.</p></div></div>
        <div className="journey-lines">
          <Link href="/supervisor" className="journey-link supervisor-journey"><span className="section-index">SITE OPERATIONS / SUPERVISOR</span><strong>Understand the restriction.<br/>Commit to the action.</strong><span className="journey-foot">Obligations · cited clauses · Standing Order preview <b aria-hidden="true">↗</b></span></Link>
          <Link href="/worker" className="journey-link worker-journey"><span className="section-index">PERSONAL RECORD / WORKER</span><strong>Know why work stopped.<br/>Confirm for yourself.</strong><span className="journey-foot">Mobile Parchi · Hindi & English · own acknowledgement <b aria-hidden="true">↗</b></span></Link>
        </div>
        <div className="boundaries-row"><Link href="/cedar">Authorization lab <span>Real Cedar decisions ↗</span></Link><Link href="/facilitator">Consent & privacy <span>Redacted assistance ↗</span></Link><Link href="/impact">Documented impact <span>Public, aggregate data ↗</span></Link></div>
      </section>

      <footer className="experience-footer"><span>AADHESH <i className="footer-mark"/></span><p>Environmental operations, grounded in verifiable evidence.</p><span>LOCAL DEMONSTRATION · NOT LEGAL ADVICE</span></footer>
    </div>
  );
}
