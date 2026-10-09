const ORDINALS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

export function stageName(stage: number | "NONE" | null): string {
  if (stage === null || stage === "NONE") return "No stage";
  return `Stage ${ORDINALS[stage] ?? stage}`;
}

export function shortHash(hash?: string | null): string {
  if (!hash) return "—";
  return `${hash.slice(0, 8)}…`;
}

export function formatInstant(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(d);
}

export function freshnessLabel(freshness?: string, ageMinutes?: number): string {
  if (!freshness) return "unknown";
  if (typeof ageMinutes === "number") {
    const unit = ageMinutes < 60 ? `${ageMinutes} min` : `${Math.round(ageMinutes / 60)} h`;
    return `${freshness} · ${unit} old`;
  }
  return freshness;
}
