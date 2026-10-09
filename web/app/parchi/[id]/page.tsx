import { QRCodeSVG } from "qrcode.react";
import { DEMO_PARCHI_VIEW, PARCHI_HI, PARCHI_EN } from "@/lib/demo-seed";

type Lang = "hi" | "en";

interface ParchiPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ lang?: string }>;
}

export default async function ParchiPage({ params, searchParams }: ParchiPageProps) {
  // The seeded parchi is the demo scenario. In the real system this route would
  // hydrate from /api/worker?payload=... and acknowledge via /api/worker/acknowledge.
  // Here we render the committed fixture directly so the video is reproducible offline.
  const view = DEMO_PARCHI_VIEW;
  const resolvedParams = await searchParams;
  const lang = (resolvedParams.lang ?? "hi") as Lang;
  const copy = lang === "hi" ? PARCHI_HI : PARCHI_EN;

  const viewState = String(view.state ?? view.status ?? "");
  const acknowledged =
    viewState === "ACKNOWLEDGED" ||
    viewState === "acknowledged" ||
    viewState === "sealed";
  const stageText = view.stage ? `GRAP ${view.stage}` : "GRAP";
  const reasonBody = copy.reasonBody;

  const parchiSerial = view.parchi_id;
  const qrValue = `aadesh://parchi/${view.worker_id}/${view.parchi_id}`;

  return (
    <div className="phone-surface safe-top safe-bottom min-h-screen bg-concrete-900 flex items-start justify-center px-3 py-6 sm:py-10">
      <article
        className={`parchi-card safe-left safe-right w-full max-w-xs overflow-hidden ${
          acknowledged ? "" : ""
        }`}
      >
        {/* ---- perforated / deckle top edge ---- */}
        <div
          className="perforation-top inline-block w-full border-t-2 border-dashed border-paper-edge"
          aria-hidden
        />

        {/* ---- stamped header: serial + title in ink, with a perforated divider ---- */}
        <header className="parchi-card-head px-4 pt-4 pb-2">
          <div className="flex items-center justify-between gap-2">
            <span className="micro-label" style={{ color: "var(--stamp-ink)" }}>
              पर्ची · Parchi
            </span>
            <span
              className="serial text-xs tabular"
              style={{ color: "var(--stamp-ink)" }}
            >
              {parchiSerial}
            </span>
          </div>
          <div className="mt-1 h-px bg-paper-edge" aria-hidden />
        </header>

        {/* ---- status line: the biggest text on the card, outdoors at arm's length ---- */}
        <div
          className={`parchi-status-line px-4 pb-3 pt-1 text-stamp-ink ${
            acknowledged ? "text-stamp-blue" : "text-stamp-ink"
          }`}
        >
          {acknowledged ? (
            copy.ackedTitle
          ) : (
            copy.title
          )}
        </div>

        <div className="px-4 pb-2">
          <p
            className={`parchi-body ${
              lang === "hi" ? "font-deva parchi-bodyHi" : "parchi-body"
            } ${acknowledged ? "text-stamp-blue" : "text-stamp-ink"}`}
          >
            {acknowledged ? copy.ackedSub : copy.sub}
          </p>
        </div>

        {!acknowledged && (
          <div
            className="mx-4 mb-3 inline-flex items-center gap-1.5 self-start border border-stamp-red bg-stamp-red/8 px-2.5 py-1 tabular rounded-none text-stamp-red"
            style={{
              color: "var(--stamp-red)",
              borderColor: "var(--stamp-red)",
              backgroundColor: "var(--stamp-red)",
              opacity: 0.08,
            }}
          >
            <span className="tabular font-semibold uppercase">{copy.pending}</span>
          </div>
        )}

        {/* ---- what you are owed, with the clause behind it ---- */}
        <dl className="mx-4 mb-4 grid gap-2 border border-paper-edge bg-paper/40 px-3 py-3">
          <div className="grid gap-0.5">
            <dt className="micro-label" style={{ color: "var(--stamp-ink)" }}>
              {copy.date}
            </dt>
            <dd
              className="tabular text-sm text-stamp-ink"
              style={{ color: "var(--stamp-ink)" }}
            >
              Today
            </dd>
          </div>
          <div className="grid gap-0.5">
            <dt className="micro-label" style={{ color: "var(--stamp-ink)" }}>
              {copy.site}
            </dt>
            <dd
              className="tabular text-sm text-stamp-ink font-mono"
              style={{ color: "var(--stamp-ink)" }}
            >
              {view.site_id}
            </dd>
          </div>
          <div className="grid gap-0.5">
            <dt className="micro-label" style={{ color: "var(--stamp-ink)" }}>
              {copy.reason}
            </dt>
            <dd
              className={`text-sm ${
                lang === "hi" ? "font-deva" : ""
              } text-stamp-ink`}
              style={{ color: "var(--stamp-ink)" }}
            >
              {reasonBody(stageText)}
            </dd>
          </div>
          <div className="grid gap-0.5">
            <dt className="micro-label" style={{ color: "var(--stamp-ink)" }}>
              {copy.clause}
            </dt>
            <dd
              className="tabular text-sm text-stamp-ink font-mono"
              style={{ color: "var(--stamp-ink)" }}
            >
              {view.obligation_ids?.length
                ? view.obligation_ids.join(", ")
                : stageText}
            </dd>
          </div>
        </dl>

        {/* ---- readiness checklist: checkboxes ---- */}
        {view.readiness_checklist && view.readiness_checklist.length > 0 && (
          <section className="mx-4 mb-4">
            <h2
              className="micro-label text-stamp-ink mb-2"
              style={{ color: "var(--stamp-ink)" }}
            >
              {copy.checklist}
            </h2>
            <ul className="grid gap-2">
              {view.readiness_checklist.map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-2 text-sm text-stamp-ink"
                  style={{ color: "var(--stamp-ink)" }}
                >
                  <span
                    className="mt-1 h-1.5 w-1.5 shrink-0 rounded-none border border-stamp-ink"
                    style={{ borderColor: "var(--stamp-ink)" }}
                    aria-hidden
                  />
                  <span
                    className={
                      lang === "hi" ? "font-deva" : ""
                    }
                  >
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* ---- the parchi QR, reproduced small ---- */}
        <div className="mx-4 mb-4 flex justify-center">
          <div
            className="inline-flex items-center gap-2 border border-stamp-ink/20 bg-white/40 px-2 py-1 text-xs tabular"
            style={{ borderColor: "var(--stamp-ink)", color: "var(--stamp-ink)" }}
          >
            <span className="tabular" style={{ color: "var(--stamp-ink)" }}>
              Scan with your phone
            </span>
          </div>
          <div className="mt-2 flex justify-center">
            <QRCodeSVG
              value={qrValue}
              size={88}
              level="M"
              bgColor="#f6f1e4"
              fgColor="#1a1a18"
              includeMargin
            />
          </div>
        </div>

        {/* ---- the single large acknowledge button in the thumb zone ---- */}
        {!acknowledged && (
          <div className="mx-4 mb-4">
            <button
              type="button"
              className="acknowledge-button w-full rounded-none border-2 border-stamp-blue bg-stamp-blue text-white tabular font-semibold tracking-wide transition-colors hover:bg-stamp-blue/90 active:translate-y-[1px] active:shadow-none"
              style={{
                backgroundColor: "var(--stamp-blue)",
                borderColor: "var(--stamp-blue)",
                color: "#fff",
              }}
            >
              {copy.acknowledge}
            </button>
            <p className="mt-2 text-center text-xs leading-relaxed" style={{ color: "var(--stamp-ink)" }}>
              Only you — the worker named on this parchi — can confirm it.
            </p>
          </div>
        )}

        {/* ---- the stamp: a visible, satisfying state change after acknowledgement ---- */}
        {acknowledged && (
          <div className="stamp stampBlue text-center py-3 px-2" style={{ color: "var(--stamp-blue)", borderColor: "var(--stamp-blue)" }}>
            <div className="tabular text-sm font-semibold tracking-widest" style={{ color: "var(--stamp-blue)" }}>
              {copy.ackedTitle}
            </div>
            <div className="tabular text-xs mt-1 opacity-80" style={{ color: "var(--stamp-blue)" }}>
              {copy.ackedSub}: 2026-10-09 09:18 IST
            </div>
          </div>
        )}

        {/* ---- footer on the parchi: the disclaimer the brief demands ---- */}
        <div className="mt-4 border-t border-paper-edge px-4 py-2 text-center text-xs leading-relaxed" style={{ color: "var(--stamp-ink)" }}>
          Not a government application. Not legal advice. Aadesh does not file claims.
          This parchi records your own statement; the record is then frozen over a content hash.
          <br />
          IBM Plex Sans + Plex Sans Devanagari · Field Instrument
        </div>

        {/* ---- perforated / deckle bottom edge ---- */}
        <div
          className="perforation-bottom block w-full border-b-2 border-dashed border-paper-edge"
          aria-hidden
        />
      </article>
    </div>
  );
}
