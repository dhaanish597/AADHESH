"use client";

import type { ApiFailure } from "@/lib/api";
import type { ObligationStatus } from "@/lib/types";

/* ------------------------------------------------------------------ icons */
type IconProps = { className?: string };

const base = "h-4 w-4";

export const IconShield = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconAlert = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M12 4l9 16H3L12 4z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M12 10v4M12 17h.01" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconCheck = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);
export const IconX = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);
export const IconFile = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconUsers = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M16 19v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 10a3 3 0 100-6 3 3 0 000 6zM16 11a3 3 0 100-6" stroke="currentColor" strokeWidth="1.6" />
    <path d="M21 19v-1a4 4 0 00-3-3.87" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconTerminal = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M4 5h16v14H4z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M7 9l3 3-3 3M13 15h4" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconLock = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M6 10V8a6 6 0 1112 0v2" stroke="currentColor" strokeWidth="1.6" />
    <rect x="4" y="10" width="16" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);
export const IconChevron = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);
export const IconArrow = ({ className = base }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
    <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);

/* ----------------------------------------------------------------- panels */

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`border border-line bg-panel shadow-panel ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-dim">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function KeyValue({
  k,
  children,
  mono = true,
}: {
  k: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 border-b border-line/60 py-2 last:border-b-0">
      <dt className="label pt-0.5">{k}</dt>
      <dd className={`min-w-0 break-words text-sm text-ink ${mono ? "data" : ""}`}>{children}</dd>
    </div>
  );
}

/* ----------------------------------------------------------------- pills */

type Tone = "danger" | "warn" | "ok" | "na" | "info" | "neutral";

const TONE: Record<Tone, string> = {
  danger: "border-danger/50 bg-danger/10 text-danger",
  warn: "border-accent/50 bg-accent/10 text-accent",
  ok: "border-success/50 bg-success/10 text-success",
  na: "border-na/50 bg-na/10 text-slate-300",
  info: "border-info/50 bg-info/10 text-info",
  neutral: "border-lineStrong bg-panelAlt text-dim",
};

export function Pill({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function obligationView(
  status: ObligationStatus,
  applicable: boolean | null,
): { label: string; tone: Tone } {
  if (status === "NOT_MET" && applicable) return { label: "Required", tone: "danger" };
  if (status === "MET") return { label: "Met", tone: "ok" };
  if (status === "UNKNOWN") return { label: "Unknown", tone: "warn" };
  return { label: "Not applicable", tone: "na" };
}

/* ----------------------------------------------------------------- buttons */

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const styles: Record<string, string> = {
    primary:
      "border-accent bg-accent text-black hover:bg-amber-400 disabled:opacity-40",
    secondary: "border-lineStrong bg-panelAlt text-ink hover:border-accent hover:text-accent",
    danger: "border-danger bg-danger/15 text-danger hover:bg-danger/25",
    ghost: "border-transparent text-dim hover:text-ink",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 border px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

/* ----------------------------------------------------------------- citation */

export function CitationBlock({
  sourceDoc,
  page,
  quote,
  hash,
}: {
  sourceDoc: string;
  page: number;
  quote: string;
  hash?: string | null;
}) {
  return (
    <div className="border border-line bg-panelAlt p-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 data text-[12px] text-dim">
        <span className="text-ink">{sourceDoc}</span>
        <span className="text-faint">page {page}</span>
        {hash && <span className="text-faint">sha256:{hash.slice(0, 12)}…</span>}
      </div>
      <blockquote className="border-l-2 border-accent/60 pl-3 text-sm leading-relaxed text-ink/90">
        “{quote}”
      </blockquote>
      <p className="mt-2 text-[11px] text-faint">
        Quote re-proved verbatim against the hashed source bytes by <span className="data">make verify</span>.
      </p>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-dim" role="status" aria-live="polite">
      <span className="h-3 w-3 animate-pulse rounded-full bg-accent" aria-hidden />
      {label}…
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {children}
    </div>
  );
}

/**
 * The error a screen shows when a call failed.
 *
 * The "is the API running" hint is withheld unless the API genuinely never answered, because a
 * request the API refused came FROM a running API. Both facts can be true of the same screen, and
 * showing them together told a signed-out visitor that the backend was down while the header
 * beside it offered a sign-in that was all they needed.
 */
export function ApiErrorNote({ error }: { error: ApiFailure }) {
  return (
    <ErrorNote>
      {error.message}
      {error.unreachable && (
        <span className="block text-xs text-danger/80">
          Is the API running? Start it with <code className="data">make api</code>.
        </span>
      )}
    </ErrorNote>
  );
}
