"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { SessionBadge } from "@/components/SessionBadge";
import { authConfigured, readSession, type Session } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
}

function NavGlyph({ label }: { label: string }) {
  const paths: Record<string, React.ReactNode> = {
    Site: <><path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M9 9h.01M15 9h.01" /></>,
    Missions: <><path d="M9 6h11M9 12h11M9 18h11" /><path d="m3 6 1 1 2-2m-3 7 1 1 2-2m-3 7 1 1 2-2" /></>,
    Workers: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-1a6 6 0 0 1 12 0v1M16 5.2a3 3 0 0 1 0 5.6M18 14a5 5 0 0 1 3 4.6V20" /></>,
    Orders: <><path d="M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M15 3v5h4M9 13h6M9 17h6" /></>,
    Evidence: <><path d="M12 3 20 6v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    "My Parchi": <><path d="M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M15 3v5h4M9 13h6M9 17h6" /></>,
    Assistance: <><circle cx="12" cy="12" r="9" /><path d="M9.6 9a2.5 2.5 0 1 1 4.4 1.6c-1.1 1-2 1.4-2 3M12 17.5h.01" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[label] ?? paths.Site}</svg>;
}

const ROLE_NAV: Record<string, NavItem[]> = {
  supervisor: [
    { href: "/supervisor", label: "Site" },
    { href: "/supervisor?view=missions", label: "Missions" },
    { href: "/supervisor?view=workers", label: "Workers" },
    { href: "/supervisor?view=orders", label: "Orders" },
    { href: "/evidence", label: "Evidence" },
  ],
  worker: [{ href: "/worker", label: "My Parchi" }],
  facilitator: [{ href: "/facilitator", label: "Assistance" }],
};

const DEMO_NAV: NavItem[] = [
  { href: "/supervisor?demo=1", label: "Site demo" },
  { href: "/worker", label: "My Parchi" },
  { href: "/facilitator?demo=1", label: "Assistance" },
  { href: "/evidence", label: "Evidence" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const landingView = pathname === "/";
  const workerView = pathname === "/worker" || pathname === "/parchi" || pathname.startsWith("/parchi/");
  const operationsView = ["/supervisor", "/facilitator", "/site", "/evidence", "/impact", "/cedar"].some((path) => pathname === path || pathname.startsWith(`${path}/`));
  const [session, setSession] = useState<Session | null>(null);
  const [search, setSearch] = useState("");
  const [demoMode, setDemoMode] = useState(process.env.NEXT_PUBLIC_AADESH_DEMO === "1");

  useEffect(() => {
    setSession(readSession());
    setSearch(window.location.search);
    const explicitDemo = new URLSearchParams(window.location.search).get("demo") === "1";
    if (explicitDemo) window.sessionStorage.setItem("aadesh_demo", "1");
    setDemoMode(process.env.NEXT_PUBLIC_AADESH_DEMO === "1" || explicitDemo || window.sessionStorage.getItem("aadesh_demo") === "1");
  }, []);

  const navItems = session?.role
    ? ROLE_NAV[session.role] ?? []
    : authConfigured
      ? []
      : DEMO_NAV;
  const activeLink = (href: string) => {
    const [path, query] = href.split("?");
    if (pathname !== path && !pathname.startsWith(path + "/")) return false;
    if (!query) return pathname === path && !search.includes("view=");
    const expected = new URLSearchParams(query);
    return [...expected].every(([key, value]) => new URLSearchParams(search).get(key) === value);
  };

  return (
    <div className={`site-root${workerView ? " site-root-worker" : ""}${operationsView ? " site-root-operations" : ""}${landingView ? " site-root-landing" : ""}`}>
      {!workerView && !landingView && <header className="site-header">
        <Link href="/" className="site-brand" aria-label="AADHESH home">
          <span className="brand-glyph" aria-hidden="true"><i/><i/><i/></span>
          <span>AADHESH</span>
        </Link>
        <nav className="site-nav" aria-label="Primary navigation">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={(event) => {
                if (item.href.includes("?")) {
                  event.preventDefault();
                  window.location.assign(item.href);
                }
              }}
              aria-current={activeLink(item.href) ? "page" : undefined}
              className={activeLink(item.href) ? "site-nav-link site-nav-link-active" : "site-nav-link"}
            >
              <NavGlyph label={item.label} />
              {item.label}
            </Link>
          ))}
        </nav>
        <SessionBadge />
        {authConfigured && !session ? (
          <Link className="header-cta" href="/login">Sign in</Link>
        ) : session && !session.role ? (
          <span className="demo-nav-label" role="status">No role is assigned to this account</span>
        ) : session?.role && ROLE_NAV[session.role]?.length ? (
          <Link className="header-cta" href={ROLE_NAV[session.role][0].href}>
            Open workspace
          </Link>
        ) : session?.role ? (
          <span className="demo-nav-label" role="status">No workspace is available for this role</span>
        ) : (
          <span className="demo-nav-label">Demonstration routes</span>
        )}
      </header>}
      {demoMode && !landingView && (
        <aside className="demo-banner" role="status">
          <span>DEMO — seeded site, real corpus</span>
          <span>Stage III is replayed from 16 Jan 2026 and was revoked on 22 Jan 2026.</span>
          <Link href="/login">Sign in for the live console</Link>
        </aside>
      )}
      <main className="site-main">{children}</main>
      {!landingView && <footer className="app-legal">Not a government application. Not legal advice. We do not file claims.</footer>}
      {!workerView && !landingView && navItems.length > 0 && <nav className="site-bottom-nav" aria-label={session?.role ? `${session.role} navigation` : "Demonstration navigation"}>
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={(event) => {
              if (item.href.includes("?")) {
                event.preventDefault();
                window.location.assign(item.href);
              }
            }}
            aria-current={activeLink(item.href) ? "page" : undefined}
            className={activeLink(item.href) ? "site-bottom-link site-bottom-link-active" : "site-bottom-link"}
          >
            <NavGlyph label={item.label} />
            {item.label}
          </Link>
        ))}
      </nav>}
    </div>
  );
}
