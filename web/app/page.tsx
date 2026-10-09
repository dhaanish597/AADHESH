import Link from "next/link";
import { Panel, Pill, IconArrow } from "@/components/ui";

const ROLES = [
  {
    href: "/supervisor",
    role: "Supervisor",
    q: "What is happening at my site and what do I need to do?",
    body: "The invoked GRAP stage, the cited obligations it activates, the Standing Order pre-commitment, and worker impact.",
  },
  {
    href: "/worker",
    role: "Worker",
    q: "Why was my work stopped today?",
    body: "A mobile-first parchi screen in Hindi and English, with the cited clause and an explicit acknowledgement.",
  },
  {
    href: "/impact",
    role: "Public impact",
    q: "How does Aadesh document the execution of GRAP restrictions?",
    body: "An aggregate, anonymous view of documented compliance activity — Standing Orders, regulated halts, restricted activities, and worker displacement. Not an AQI dashboard, not a pollution prediction.",
  },
  {
    href: "/cedar",
    role: "Authority",
    q: "Who is allowed to do this?",
    body: "Real Cedar 4.x policies evaluated in-process: a supervisor cannot acknowledge a worker's parchi.",
  },
  {
    href: "/facilitator",
    role: "Facilitator",
    q: "How can I help without the worker's record?",
    body: "A redacted assist view under live worker consent. Opting in to help is not opting in to disclosure.",
  },
  {
    href: "/verify",
    role: "Verification",
    q: "Can any of this be trusted?",
    body: "make verify re-proves every citation against hashed source bytes. The tamper check is shown failing on purpose.",
  },
];

export default function OverviewPage() {
  return (
    <div className="mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-12">
      <header className="border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold tracking-tight">Aadesh</h1>
          <Pill tone="warn">Not an AQI dashboard</Pill>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-dim">
          An environmental compliance execution system for Delhi-NCR construction sites under
          GRAP. The primary question is <span className="text-ink">“what is happening at my
          site and what do I need to do?”</span> — not “what is today&apos;s AQI?”. Every
          enforcement-relevant decision traces back to an authoritative source, a deterministic
          rule, an authorization decision, and a human acknowledgement.
        </p>
      </header>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {ROLES.map((r) => (
          <Link key={r.href} href={r.href} className="group">
            <Panel
              className="h-full transition-colors duration-200 group-hover:border-accent"
              title={r.role}
              subtitle={r.q}
            >
              <p className="text-sm leading-relaxed text-dim">{r.body}</p>
              <span className="mt-4 inline-flex items-center gap-2 text-sm text-accent">
                Open <IconArrow className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </span>
            </Panel>
          </Link>
        ))}
      </div>

      <Panel className="mt-6" title="What this deliberately is not">
        <ul className="grid gap-2 text-sm text-dim sm:grid-cols-2">
          {[
            "No giant map as the primary screen",
            "No charts everywhere, no AQI gauge as the hero",
            "No animated pollution graphics",
            "No generic AI chat interface",
            "No monetary entitlement unless a hashed source establishes it",
            "Not legal advice and not a government application",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 bg-danger" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
