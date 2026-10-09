"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { X, Check, Shield, EnvelopeSimple, TreeEvergreen, Leaf } from "@phosphor-icons/react/ssr";
import { DEMO_SUPERVISOR_PAYLOAD, DEMO_WORKERS, DEMO_STANDING_ORDER } from "@/lib/demo-seed";
import { formatInstant, shortHash, stageName } from "@/lib/format";
import { Qr } from "@/components/Qr";

/* --------------------------------------------------------------------------
   One seeded demo scenario. Replace this with the live /api/supervisor response
   when the API is up; the component is written to accept either shape, so the
   "Live corpus" toggle in the existing supervisor route can be wired in later
   without touching this screen's layout.
   ----------------------------------------------------------------------- */

function OrdinalBadge({ stage }: { stage: number }) {
  return (
    <span
      className="console-panel console-panel-head inline-flex items-center gap-2 px-3 py-1.5"
      aria-label={`Stage ${stage}`}
    >
      <span className="micro-label text-caution">Stage</span>
      <span className="font-mono text-sm font-semibold tabular text-steel-100">
        {stageName(stage)}
      </span>
    </span>
  );
}

/** Status glyph: a single SVG drawn in our state colours. Never colour alone. */
function StateGlyph({
  kind,
  label,
}: {
  kind: "permitted" | "stopped" | "caution";
  label: string;
}) {
  const colour =
    kind === "permitted" ? "var(--clear)" : kind === "stopped" ? "var(--halt)" : "var(--caution)";
  const glyph =
    kind === "permitted" ? (
      <Check className="h-5 w-5" weight="bold" />
    ) : kind === "stopped" ? (
      <X className="h-5 w-5" weight="bold" />
    ) : (
      <Leaf className="h-5 w-5" weight="fill" />
    );
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="tabular text-sm font-semibold"
        style={{ color: colour }}
        aria-hidden
      >
        {glyph}
      </span>
      <span className="micro-label" style={{ color: colour }}>
        {label}
      </span>
    </span>
  );
}

/* --------------------------------------------------------------------------
   Hero number: mono, large, tabular, with a micro-label eyebrow above.
   One display size per screen — the two hero numbers share the same size.
   ----------------------------------------------------------------------- */

function HeroNumber({
  value,
  label,
}: {
  value: string;
  label: string;
}) {
  return (
    <div className="console-panel flex flex-col gap-2 px-4 py-3">
      <span className="micro-label text-steel-500">{label}</span>
      <span className="font-mono text-3xl font-semibold tabular text-steel-100 leading-none">
        {value}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Obligation row: action-first, legal quote secondary and never equal weight.
   ----------------------------------------------------------------------- */

function ObligationRow({
  obligation,
}: {
  obligation: typeof DEMO_SUPERVISOR_PAYLOAD.obligations[number];
}) {
  const [open, setOpen] = useState(false);
  const applicable = obligation.applicable === true;
  const statusRaw = obligation.status;
  const status = (statusRaw as string) || "UNKNOWN";
  const isMet = status === "MET";
  const isRequired = status === "NOT_MET" && applicable;

  const statusColor =
    isRequired
      ? "var(--halt)"
      : isMet
      ? "var(--clear)"
      : applicable
      ? "var(--caution)"
      : "var(--steel-500)";

  const statusLabel =
    isRequired
      ? "Stops now"
      :    applicable
      ? isMet
        ? "Met"
        : "Stops now"
      : "Out of scope";

  return (
    <section className="obligation-row">
      <div className="obligation-row-head flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2 flex-wrap">
            <StateGlyph kind={isRequired ? "stopped" : isMet ? "permitted" : "caution"} label={statusLabel} />
            {obligation.issues_parchi && (
              <span className="micro-label text-evidence">Parchi issued</span>
            )}
            <span className="clause-id clause-idStrong tabular">{obligation.obligation_id}</span>
          </div>
          <h3 className="font-sans text-base font-semibold leading-snug text-steel-100">
            {obligation.label}
          </h3>
          <p className="mt-1.5 text-sm leading-relaxed text-steel-300">
            {obligation.required_action}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-steel-500">{obligation.reason}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="micro-label text-steel-500">Clause</div>
          <div className="clause-id clause-idStrong tabular mt-0.5">{obligation.source_doc}</div>
          <div className="clause-id tabular mt-0.5 text-steel-500">page {obligation.source_page}</div>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium tabular transition-colors hover:text-caution"
            style={{ color: "var(--steel-300)" }}
          >
            {open ? "Hide source" : "View source"}
          </button>
        </div>
      </div>
      {open && (
        <div className="obligation-row-body border-t border-rule">
          <blockquote className="pl-3 border-l-2 border-caution" style={{ borderLeftColor: "var(--caution)" }}>
            <p className="text-sm leading-relaxed text-steel-300">
              “{obligation.source_quote}”
            </p>
          </blockquote>
          <p className="mt-2 tabular text-xs text-steel-500">
            {obligation.source_doc} · page {obligation.source_page} · sha256:{" "}
            {shortHash(obligation.source_hash)}
          </p>
        </div>
      )}
    </section>
  );
}

/* --------------------------------------------------------------------------
   Crew tile: one worker, one state. The grid filling up is the demo climax.
   ----------------------------------------------------------------------- */

function CrewTile({ worker }: { worker: typeof DEMO_WORKERS[number] }) {
  const workerState = worker.state;
  const s = String(workerState ?? "");
  const acknowledged = s === "acknowledged" || s === "sealed";

  const serial = worker.parchi_id ?? "—";

  return (
    <button
      type="button"
      className={`crew-tile ${acknowledged ? "crew-tileAcknowledged" : "crew-tilePending"} flex h-24 flex-col justify-between gap-2 px-3 text-left transition-colors`}
      aria-pressed={acknowledged}
      aria-label={`${worker.display_name}, ${s === "acknowledged" || s === "sealed" ? "acknowledged" : "pending acknowledgement"}, parchi ${serial}`}
    >
      <div className="flex items-center justify-between">
        <span className="tabular text-xs text-steel-500 truncate">{worker.display_name}</span>          {acknowledged ? (
                          <span className="inline-flex items-center gap-1 tabular text-xs font-semibold" style={{ color: "var(--clear)" }}>
                            <Check className="h-3.5 w-3.5" weight="bold" />
                            acked
                          </span>
        ) : worker.registered ? (
          <span className="micro-label text-steel-500">reg</span>
        ) : (
          <span className="micro-label text-steel-500">no reg</span>
        )}
      </div>
      <div className="tabular text-xs text-steel-500 truncate">{serial}</div>
    </button>
  );
}

/* --------------------------------------------------------------------------
   ISSUE HALT: a deliberate, consequential action. Hold-to-confirm, not a plain
   click. The button gives physical feedback on press.
   ----------------------------------------------------------------------- */

function HoldToConfirm({
  onConfirm,
  busy,
}: {
  onConfirm: () => void;
  busy: boolean;
}) {
  const [held, setHeld] = useState(false);
  const [count, setCount] = useState(0);

  const clear = useCallback((hover?: boolean) => {
    setHeld(false);
    setCount(0);
  }, []);

  // We implement hold via pointer events on the button itself.
  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      // Capture so a pointer move off the button doesn't cancel the hold.
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      if (busy) {
        clear();
        return;
      }
      setHeld(true);
      const t = setInterval(() => setCount((c) => c + 1), 1000);
      // Require a 3-second hold.
      const timeout = setTimeout(() => {
        onConfirm();
        clear();
        clearInterval(t);
      }, 3000);
      return () => {
        clearTimeout(timeout);
        clearInterval(t);
      };
    },
    [busy, onConfirm, clear],
  );

  const onPointerUp = useCallback(() => {
    clear();
  }, [clear]);

  const onPointerLeave = useCallback(() => {
    clear();
  }, [clear]);

  const fraction = Math.min(1, count / 3);

  return (
    <button
      type="button"
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerLeave}
      disabled={busy}
      className="acknowledge-button relative overflow-hidden rounded-none border-2 border-halt bg-halt text-concrete-900 font-mono font-semibold tabular transition-transform hover:translate-x-[-1px] hover:translate-y-[-1px] hover:shadow-[4px_4px_0px_0px_var(--concrete-900)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-[1px_1px_0px_0px_var(--concrete-900)] disabled:cursor-not-allowed disabled:opacity-40"
      aria-label="Hold to issue a halt order. Requires a three-second hold to confirm."
    >
      {/* progress fill, clipped to the left */}
      <span
        className="absolute inset-0 h-full w-full bg-halt transition-[width] duration-150"
        style={{
          width: `${fraction * 100}%`,
          opacity: 0.15,
        }}
        aria-hidden
      />
      <span className="relative">
        {busy ? (
          "Issuing…"
        ) : held ? (
          <span className="flex items-center gap-2">
            <span className="tabular text-concrete-900 text-lg">{count}</span>
            <span className="tabular text-concrete-900">hold…</span>
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <Shield className="h-5 w-5" weight="bold" />
            Hold to issue halt
          </span>
        )}
      </span>
    </button>
  );
}

/* --------------------------------------------------------------------------
   Supervisor console — /site.
   Full-bleed state banner first, then provenance line, then the two hero
   numbers, then obligations, standing order, and the crew board.
   ----------------------------------------------------------------------- */

const inThreeHours = new Date(Date.now() + 3 * 60 * 60 * 1000);

export default function SitePage() {
  const [order, setOrder] = useState<typeof DEMO_STANDING_ORDER | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // The seeded data is the initial truth. When the API is up we swap the source;
  // for now this screen is fully offline and reproducible from the committed fixture.
  const data = DEMO_SUPERVISOR_PAYLOAD;
  const workers = DEMO_WORKERS;

  const acknowledgedCount = useMemo(() =>
    workers.reduce(
      (n, w) =>
        n + (String(w.state ?? "") === "acknowledged" ||
          String(w.state ?? "") === "sealed"
          ? 1
          : 0),
      0,
    ),
  [workers]);
  const total = workers.length;
  const rupees = "₹1,02,000";

  const issueHalt = useCallback(async () => {
    setBusy(true);
    setNotice(null);
    // In the real system this POSTs to /api/standing-order. For the seeded demo
    // we flip local state so the screen is watchable without a backend.
    await new Promise((r) => setTimeout(r, 600));
    setOrder(DEMO_STANDING_ORDER);
    setNotice("Halt order issued. One parchi opened per rostered worker.");
    setBusy(false);
  }, []);

  const officialStageNum =
    typeof data.official_stage === "number" ? data.official_stage : 0;
  const noInvocation = officialStageNum === 0;
  const bannerKind = (noInvocation ? "caution" : "stopped") as "permitted" | "stopped" | "caution";
  const bannerClass =
    bannerKind === "permitted"
      ? "state-bannerPermitted"
      : bannerKind === "stopped"
      ? "state-bannerStopped"
      : "state-bannerCaution";
  const bannerIsPermitted = bannerKind === "permitted";

  const bannerText =
    noInvocation
      ? "No invocation"
      : "Work " + (bannerKind === "permitted" ? "permitted" : "stopped");
  const provenanceColour = data.stage_detail.discrepancy ? "var(--caution)" : "var(--steel-500)";

  return (
    <div className="mx-auto max-w-5xl px-4 py-5 lg:px-6 lg:py-6">
      {/* ---- state banner: the squint-test anchor. Full-bleed within the column. ---- */}
      <div className={"state-banner w-full " + bannerClass}>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <StateGlyph kind={bannerKind} label={bannerText} />
            <span
              className="font-mono text-2xl font-semibold tabular tracking-wide"
              style={{ color: bannerIsPermitted ? undefined : "var(--concrete-900)" }}
            >
              {bannerText.toUpperCase()}
            </span>
          </div>
          <OrdinalBadge stage={officialStageNum} />
        </div>
      </div>

      {/* ---- provenance line: one line, mono, small, directly under the banner. ---- */}
      <div
        className={`provenance-line ${data.stage_detail.discrepancy ? "provenance-lineCaution" : ""} mb-6 tabular`}
        style={data.stage_detail.discrepancy ? { color: provenanceColour } : undefined}
      >
        <span className="inline-flex items-center gap-1.5">
          <span className="tabular font-semibold">{stageName(data.official_stage)}</span>
          <span aria-hidden>·</span>
          <span className="tabular">invoked by {data.official_invocation?.citation?.source_doc}</span>
          <span aria-hidden>·</span>
          <span className="tabular">sha256 {shortHash(data.official_invocation?.citation?.source_hash)}</span>
          <span aria-hidden>·</span>
          <span className="tabular">{data.reading?.station_id} station {data.reading?.value} at {formatInstant(data.reading?.observed_at)}</span>
          <span aria-hidden>·</span>
          <span className="tabular">{data.stage_detail.is_replay ? "replay" : "fresh"}</span>
        </span>
        {data.stage_detail.discrepancy && (
          <span className="ml-3 tabular text-xs font-semibold" style={{ color: "var(--caution)" }}>
            implied stage matches — order is the legal trigger
          </span>
        )}
      </div>

      {/* ---- two hero numbers. One display size per screen. ---- */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <HeroNumber value={rupees} label="Entitlement documented" />
        <HeroNumber value={`${acknowledgedCount} / ${total} workers acknowledged`} label="Crew acknowledged" />
      </div>

      {/* ---- obligations: action-first, legal quote secondary. ---- */}
      <section className="mb-6 console-panel">
        <div className="console-panel-head flex items-center justify-between gap-4">
          <div>
            <h2 className="font-sans text-sm font-semibold tracking-tight text-steel-100">
              Your obligations
            </h2>
            <p className="micro-label mt-0.5 text-steel-500">
              {data.summary.applicable} applicable · {data.summary.out_of_scope} out of scope
            </p>
          </div>
        </div>
        <div className="divide-y divide-rule">
          {data.obligations.map((o) => (
            <ObligationRow key={o.obligation_id} obligation={o} />
          ))}
        </div>
      </section>

      {/* ---- standing order: armed or not, with scope and expiry. ---- */}
      <section className="mb-6 console-panel">
        <div className="console-panel-head flex items-center justify-between gap-4">
          <div>
            <h2 className="font-sans text-sm font-semibold tracking-tight text-steel-100">
              Standing Order
            </h2>
            <p className="micro-label mt-0.5 text-steel-500">
              Signed · narrow · time-bounded — not an autonomous permission
            </p>
          </div>
          {order ? (              <span className="inline-flex items-center gap-1.5 micro-label tabular px-2 py-0.5 border border-caution text-caution"
              style={{ color: "var(--caution)", borderColor: "var(--caution)" }}
            >
              <Leaf className="h-3 w-3" weight="fill" />
              Armed
            </span>
          ) : (
            <span className="micro-label text-steel-500">Not armed</span>
          )}
        </div>

        {order ? (
          <dl className="grid gap-3 px-4 py-3 sm:grid-cols-2">
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Order id</span>
              <dd className="tabular text-sm text-steel-300">{order.standing_order_id}</dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Trigger</span>
              <dd className="tabular text-sm text-steel-300">
                {stageName(order.trigger.stage)} · {order.trigger.match}
              </dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Actions</span>
              <dd className="tabular text-sm text-steel-300">
                {order.actions.map((a) => a.action).join(" + ")}
              </dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Expires</span>
              <dd className="tabular text-sm text-steel-300">{formatInstant(order.valid_until)}</dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Signed by</span>
              <dd className="tabular text-sm text-steel-300">{order.supervisor_id}</dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Signed at</span>
              <dd className="tabular text-sm text-steel-300">{formatInstant(order.signed_at)}</dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Commitment hash</span>
              <dd className="tabular text-xs text-steel-500">{shortHash(order.commitment_hash)}</dd>
            </div>
            <div className="grid gap-1">
              <span className="micro-label text-steel-500">Trigger fingerprint</span>
              <dd className="tabular text-xs text-steel-500">{shortHash(order.trigger_fingerprint)}</dd>
            </div>
          </dl>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
            <p className="text-sm text-steel-300 max-w-xl">
              Arm a narrow, time-bounded pre-commitment now so a verified Stage III invocation
              fires the dust-work halt and opens one parchi per rostered worker without waiting
              on you.
            </p>
            <HoldToConfirm onConfirm={issueHalt} busy={busy} />
          </div>
        )}

        {notice && (
          <p className="border-t border-rule px-4 py-3 flex items-start gap-2 text-sm">
            <span
              className="shrink-0 tabular text-base font-semibold"
              style={{ color: "var(--clear)" }}
              aria-hidden
            >
              <Check weight="bold" />
            </span>
            <span className="text-steel-300">{notice}</span>
          </p>
        )}
      </section>

      {/* ---- crew board: the demo climax. ---- */}
      <section className="mb-6 console-panel">
        <div className="console-panel-head flex items-center justify-between gap-4">
          <div>
            <h2 className="font-sans text-sm font-semibold tracking-tight text-steel-100">
              Crew board
            </h2>
            <p className="micro-label mt-0.5 text-steel-500">
              34 workers · one tile each · acknowledgement fills the board
            </p>
          </div>
          <span
            className="inline-flex items-center gap-1.5 tabular font-mono text-sm font-semibold"
            style={{ color: "var(--clear)" }}
          >
            <Check className="h-4 w-4" weight="bold" />
            {acknowledgedCount}/{total}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 px-4 pb-4">
          {workers.map((w) => (
            <CrewTile key={w.worker_id} worker={w} />
          ))}
        </div>

        <p className="micro-label text-steel-500 border-t border-rule px-4 py-3">
          Each tile is a worker. A tile turns green and checks when that worker scans their
          parchi and confirms in their own name. The supervisor cannot acknowledge on their
          behalf — that is the Cedar denial on the Authority screen.
        </p>
      </section>

      {/* ---- QR wall entry: one button to the handoff surface. ---- */}
      <section className="console-panel px-4 py-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="font-sans text-sm font-semibold tracking-tight text-steel-100">
              QR wall
            </h2>
            <p className="micro-label mt-0.5 text-steel-500">
              One QR per worker · hold up or project · scan from a metre away
            </p>
          </div>
          <a
            href="/handoff"
            className="inline-flex items-center gap-2 tabular font-medium border border-evidence text-evidence hover:bg-evidence hover:text-concrete-900 px-3 py-1.5 transition-colors"
          >
            <TreeEvergreen className="h-4 w-4" />
            Open QR wall
          </a>
        </div>
      </section>

      {/* ---- footer on every screen: the disclaimer the brief demands. ---- */}
      <footer className="mt-8 border-t border-rule pt-4 text-center text-xs text-steel-500">
        Not a government application. Not legal advice. Aadesh does not file claims.
        This clause applies to your site; it does not, on its own, create any payment.
        <br />
        Hindi priority · IBM Plex Sans + Plex Sans Devanagari + Plex Mono · design direction:
        Field Instrument.
      </footer>
    </div>
  );
}
