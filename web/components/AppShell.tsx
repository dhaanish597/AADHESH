"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Overview", hint: "Roles" },
  { href: "/supervisor", label: "Supervisor", hint: "What do I do?" },
  { href: "/worker", label: "Worker", hint: "पर्ची / Parchi" },
  { href: "/impact", label: "Public impact", hint: "Public" },
  { href: "/cedar", label: "Authority", hint: "Cedar denials" },
  { href: "/facilitator", label: "Facilitator", hint: "Redacted view" },
  { href: "/verify", label: "Verification", hint: "make verify" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">        <aside className="lg:w-60 lg:shrink-0 border-b lg:border-b-0 lg:border-r border-rule bg-concrete-800">
        <div className="flex items-center gap-3 px-4 py-4 lg:py-6">
          <div
            aria-hidden
            className="grid h-9 w-9 place-items-center border border-rule bg-concrete-700 font-mono text-evidence"
          >
            आ
          </div>
          <div>
            <div className="font-mono text-sm font-semibold tracking-tight text-steel-100">Aadesh</div>
            <div className="micro-label text-steel-500">GRAP execution</div>
          </div>
        </div>
        <nav aria-label="Primary" className="flex flex-row gap-1 overflow-x-auto px-2 pb-2 lg:flex-col lg:px-2 lg:pb-6">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-w-max items-baseline gap-2 border-l-2 px-3 py-2 transition-colors duration-200 ${
                  active
                    ? "border-evidence bg-concrete-800 text-steel-100"
                    : "border-transparent text-steel-500 hover:border-rule hover:text-steel-300"
                }`}
              >
                <span className="text-sm font-medium">{item.label}</span>
                <span className="hidden text-[11px] text-steel-500 lg:inline">{item.hint}</span>
              </Link>
            );
          })}
        </nav>
        <div className="hidden px-4 lg:block">
          <p className="text-[11px] leading-relaxed text-steel-500">
            Aadesh is not an AQI dashboard, not a prediction system and not legal advice. Every
            clause shown is cited to a hashed CAQM source.
          </p>
        </div>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
