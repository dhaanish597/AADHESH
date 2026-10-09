"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, ErrorNote, IconCheck, IconLock, Loading, Pill } from "@/components/ui";
import { postJson } from "@/lib/api";
import { formatInstant, stageName } from "@/lib/format";
import type { WorkerView } from "@/lib/types";

type Lang = "hi" | "en";

const COPY: Record<
  Lang,
  {
    title: string;
    sub: string;
    date: string;
    site: string;
    reason: string;
    clause: string;
    checklist: string;
    acknowledge: string;
    ackedTitle: string;
    ackedSub: string;
    reasonBody: (stage: string, replay: boolean) => string;
    pending: string;
    sealed: string;
    dateUnavailable: string;
    replayNotice: string;
    source: string;
    sourceUnavailable: string;
    openSource: string;
    legalNote: string;
  }
> = {
  hi: {
    title: "यह आपकी पर्ची है।",
    sub: "कारण और स्रोत देखें। पुष्टि केवल आप अपने लिए करें।",
    date: "दिनांक",
    site: "स्थान",
    reason: "कारण",
    clause: "लागू धारा",
    checklist: "दस्तावेज़ जाँच-सूची",
    acknowledge: "पर्ची स्वीकार करें",
    ackedTitle: "आपकी पर्ची स्वीकार कर ली गई है।",
    ackedSub: "दर्ज समय",
    reasonBody: (stage, replay) => replay
      ? `ऐतिहासिक GRAP ${stage} डेमो रिकॉर्ड। यह वर्तमान रोक नहीं है।`
      : `लागू GRAP ${stage} के तहत धूल फैलाने वाले निर्माण कार्य पर रोक है।`,
    pending: "स्वीकृति प्रतीक्षित",
    sealed: "सीलबंद",
    dateUnavailable: "दर्ज नहीं",
    replayNotice: "यह ऐतिहासिक प्रदर्शन रिकॉर्ड है, वर्तमान सरकारी रोक नहीं।",
    source: "इस पर्ची का सरकारी स्रोत",
    sourceUnavailable: "स्रोत का सटीक उद्धरण इस रिकॉर्ड में उपलब्ध नहीं है।",
    openSource: "आधिकारिक CAQM PDF खोलें",
    legalNote: "यह पर्ची भुगतान, सरकारी दावा स्वीकृति या कानूनी सलाह नहीं है।",
  },
  en: {
    title: "This is your Parchi.",
    sub: "Review the reason and source. Confirm it only for yourself.",
    date: "Date",
    site: "Site",
    reason: "Reason",
    clause: "Applicable clause",
    checklist: "Documentation checklist",
    acknowledge: "Acknowledge Parchi",
    ackedTitle: "Your Parchi has been acknowledged.",
    ackedSub: "Recorded at",
    reasonBody: (stage, replay) => replay
      ? `Historical GRAP ${stage} demonstration record. This is not a current restriction.`
      : `Dust-generating construction activity is restricted under the invoked GRAP ${stage}.`,
    pending: "Awaiting your confirmation",
    sealed: "Sealed",
    dateUnavailable: "Not recorded",
    replayNotice: "This is a historical demonstration record, not a current government restriction.",
    source: "Official source for this Parchi",
    sourceUnavailable: "An exact source quotation is not available in this Parchi record.",
    openSource: "Open official CAQM PDF",
    legalNote: "This Parchi is not a payment, approved government claim or legal advice.",
  },
};

function readPayload(): string {
  if (typeof window === "undefined") return "";
  const payload = new URLSearchParams(window.location.hash.slice(1)).get("payload") ?? "";
  if (payload) window.history.replaceState(null, "", window.location.pathname);
  return payload;
}

export default function WorkerPage() {
  const [payload, setPayload] = useState("");
  const [lang, setLang] = useState<Lang>("en");
  const [view, setView] = useState<WorkerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPayload(readPayload());
  }, []);

  const load = useCallback(async (p: string) => {
    if (!p) return;
    setError(null);
    try {
      setView(await postJson<WorkerView>("/api/worker/view", { payload: p }));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load(payload);
  }, [payload, load]);

  const acknowledge = async () => {
    setBusy(true);
    setError(null);
    try {
      // The worker asserts who they are; Cedar and the domain both check it against the parchi.
      await postJson("/api/worker/acknowledge", { payload, worker_id: view?.worker_id });
      await load(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const t = COPY[lang];
  const acknowledged = view?.status === "ACKNOWLEDGED" || view?.state === "acknowledged" || view?.state === "sealed";
  const stageText = view?.stage ? stageName(view.stage) : "the invoked stage";
  const historicalReplay = view?.provenance === "replay";

  if (!payload) {
    return (
      <div className="worker-route mx-auto max-w-md px-5 py-12 text-center">
        <h1 className="text-lg font-semibold text-ink">No Parchi link</h1>
        <p className="mt-2 text-sm text-dim">
          Open this page by scanning the personal QR provided by your site supervisor. The link
          opens your Parchi; only you can confirm it in the worker experience.
        </p>
        <Link href="/supervisor" className="mt-6 inline-block text-sm text-accent">
          Supervisor demonstration
        </Link>
      </div>
    );
  }

  return (
    <div className="worker-route mx-auto max-w-md px-5 py-8">
      <div className="mb-4 flex items-center justify-between">
        <span className="label">Parchi · पर्ची</span>
        <div className="inline-flex border border-line" role="group" aria-label="Language">
          {(["hi", "en"] as Lang[]).map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={lang === l}
              onClick={() => setLang(l)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                lang === l ? "bg-accent text-black" : "bg-panelAlt text-dim hover:text-ink"
              }`}
            >
              {l === "hi" ? "हिन्दी" : "English"}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {!view && !error && <Loading />}

      {view && (
        <div className="space-y-5">
          <section className="border border-line bg-panel p-5">
            {acknowledged ? (
              <div className="flex items-start gap-3">
                <IconCheck className="mt-1 h-6 w-6 shrink-0 text-success" />
                <div>
                  <h1 className="text-xl font-semibold leading-snug text-ink">{t.ackedTitle}</h1>
                  <p className="mt-2 text-sm text-dim">
                    {t.ackedSub}: {formatInstant(view.acknowledged_at ?? view.sealed_at)}
                  </p>
                  {view.content_hash && (
                    <details className="mt-3 text-left">
                      <summary className="cursor-pointer text-xs text-dim">Technical record details</summary>
                      <p className="data mt-2 break-all text-[11px] text-faint">sha256:{view.content_hash}</p>
                      <p className="data mt-1 break-all text-[11px] text-faint">{view.parchi_id}</p>
                    </details>
                  )}
                </div>
              </div>
            ) : (
              <>
                <h1 className="text-2xl font-semibold leading-snug text-ink">{historicalReplay ? t.replayNotice : t.title}</h1>
                <p className="mt-2 text-sm text-dim">{t.sub}</p>
                <Pill tone="warn" className="mt-3">
                  {t.pending}
                </Pill>
              </>
            )}
          </section>

          <section className="border border-line bg-panel p-5">
            <h2 className="text-sm font-semibold text-ink">{t.source}</h2>
            {view.citations && view.citations.length > 0 ? (
              <div className="mt-3 space-y-4">
                {view.citations.map((citation) => (
                  <details key={`${citation.obligation_id}-${citation.source_doc}`} className="border border-line bg-panelAlt p-3">
                    <summary className="cursor-pointer text-sm text-ink">
                      {citation.source_title} · page {citation.source_page}
                    </summary>
                    <p className="mt-3 border-l-2 border-accent/70 pl-3 text-sm leading-relaxed text-ink">
                      “{citation.source_quote}”
                    </p>
                    <p className="data mt-3 break-all text-[10px] leading-relaxed text-faint">
                      {citation.source_doc} · SHA-256 {citation.source_hash}
                    </p>
                    <a className="mt-3 inline-flex text-xs text-accent underline underline-offset-4" href={`${citation.source_url}#page=${citation.source_page}`} target="_blank" rel="noreferrer">
                      {t.openSource} · {citation.source_page} ↗
                    </a>
                  </details>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm text-dim">{t.sourceUnavailable}</p>
            )}
          </section>

          <section className="border border-line bg-panel p-5">
            <dl className="space-y-3">
              <Row k={t.date} v={formatInstant(view.acknowledged_at ?? undefined) || t.dateUnavailable} />
              <Row k={t.site} v={view.site_label ?? "Construction site"} />
              <Row k={t.reason} v={t.reasonBody(stageText, historicalReplay)} />
              <Row
                k={t.clause}
                v={view.citations?.length ? view.citations.map((citation) => citation.source_title).join("; ") : stageText}
              />
            </dl>
            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-xs text-dim">Technical references</summary>
              <dl className="mt-3 space-y-2">
                <Row k="Site reference" v={view.site_id} mono />
                <Row k="Parchi reference" v={view.parchi_id} mono />
                <Row k="Rule references" v={view.obligation_ids?.join(", ") || "Not recorded"} mono />
              </dl>
            </details>
          </section>

          {view.readiness_checklist && view.readiness_checklist.length > 0 && (
            <section className="border border-line bg-panel p-5">
              <h2 className="text-sm font-semibold text-ink">{t.checklist}</h2>
              <ul className="mt-3 space-y-2">
                {view.readiness_checklist.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm text-dim">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 border border-accent" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {view.cites_measured_data === false && (
            <p className="border border-accent/40 bg-accent/10 p-3 text-xs text-accent">
              This record is not backed by a live station measurement
              {view.provenance ? ` (provenance: ${view.provenance})` : ""}. It is shown so the
              limitation is visible, never hidden.
            </p>
          )}

          {historicalReplay && (
            <p role="status" className="border border-accent/40 bg-accent/10 p-3 text-xs leading-relaxed text-accent">
              {t.replayNotice} This Parchi is a demonstration of the recorded workflow; it does not assert that work is stopped today.
            </p>
          )}

          {!acknowledged && (
            <Button
              onClick={acknowledge}
              disabled={busy}
              className="h-14 w-full text-base"
            >
              <IconLock className="h-5 w-5" />
              {busy ? "…" : t.acknowledge}
            </Button>
          )}

          <p className="text-center text-[11px] leading-relaxed text-faint">
            Confirming is not sealing. In this local demo, the one-time QR link identifies the
            Parchi, and the backend checks the submitted worker ID against its record. There is
            no live account sign-in here to independently verify who is holding the link. A
            supervisor cannot confirm through the supervisor screen.
          </p>
          <p className="text-center text-[11px] leading-relaxed text-faint">{t.legalNote}</p>
        </div>
      )}
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div>
      <dt className="label">{k}</dt>
      <dd className={`mt-0.5 text-sm text-ink ${mono ? "data" : ""}`}>{v}</dd>
    </div>
  );
}
