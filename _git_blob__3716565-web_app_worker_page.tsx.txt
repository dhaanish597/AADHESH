"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, ErrorNote, IconCheck, IconLock, Loading, Pill } from "@/components/ui";
import { getJson, postJson } from "@/lib/api";
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
    reasonBody: (stage: string) => string;
    pending: string;
    sealed: string;
  }
> = {
  hi: {
    title: "आज GRAP के तहत आपका काम रोका गया।",
    sub: "यह आपकी पर्ची है। इसे स्वीकार करें ताकि रोक आपके नाम पर दर्ज हो जाए।",
    date: "दिनांक",
    site: "स्थान",
    reason: "कारण",
    clause: "लागू धारा",
    checklist: "दस्तावेज़ जाँच-सूची",
    acknowledge: "पर्ची स्वीकार करें",
    ackedTitle: "आपकी पर्ची स्वीकार कर ली गई है।",
    ackedSub: "दर्ज समय",
    reasonBody: (stage) =>
      `लागू GRAP ${stage} के तहत धूल फैलाने वाले निर्माण कार्य पर रोक है।`,
    pending: "स्वीकृति प्रतीक्षित",
    sealed: "सीलबंद",
  },
  en: {
    title: "Your work was stopped today under GRAP.",
    sub: "This is your Parchi. Confirm it so the halt is recorded in your own name.",
    date: "Date",
    site: "Site",
    reason: "Reason",
    clause: "Applicable clause",
    checklist: "Documentation checklist",
    acknowledge: "Acknowledge Parchi",
    ackedTitle: "Your Parchi has been acknowledged.",
    ackedSub: "Recorded at",
    reasonBody: (stage) =>
      `Dust-generating construction activity is restricted under the invoked GRAP ${stage}.`,
    pending: "Awaiting your confirmation",
    sealed: "Sealed",
  },
};

function readPayload(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("payload") ?? "";
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
      setView(await getJson<WorkerView>(`/api/worker?payload=${encodeURIComponent(p)}`));
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

  if (!payload) {
    return (
      <div className="mx-auto max-w-md px-5 py-12 text-center">
        <h1 className="text-lg font-semibold text-ink">No Parchi link</h1>
        <p className="mt-2 text-sm text-dim">
          This screen opens from a worker&apos;s acknowledgement QR. Open the supervisor console
          and show the QR grid first.
        </p>
        <Link href="/supervisor" className="mt-6 inline-block text-sm text-accent">
          Go to supervisor console
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-5 py-8">
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
                    <p className="data mt-2 break-all text-[11px] text-faint">
                      sha256:{view.content_hash}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <>
                <h1 className="text-2xl font-semibold leading-snug text-ink">{t.title}</h1>
                <p className="mt-2 text-sm text-dim">{t.sub}</p>
                <Pill tone="warn" className="mt-3">
                  {t.pending}
                </Pill>
              </>
            )}
          </section>

          <section className="border border-line bg-panel p-5">
            <dl className="space-y-3">
              <Row k={t.date} v={formatInstant(view.acknowledged_at ?? undefined) || "Today"} />
              <Row k={t.site} v={view.site_id} mono />
              <Row k={t.reason} v={t.reasonBody(stageText)} />
              <Row
                k={t.clause}
                v={view.obligation_ids && view.obligation_ids.length ? view.obligation_ids.join(", ") : stageText}
                mono
              />
            </dl>
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
            Confirming is not sealing. Confirming records your own statement; the system then
            freezes the record over a content hash. Only you — the worker named on this Parchi —
            can confirm it.
          </p>
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
