"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { SessionBadge } from "@/components/SessionBadge";

interface NavItem {
  href: string;
  label: string;
  roles?: string[];
}

const DESKTOP_NAV: NavItem[] = [
  { href: "/site", label: "Site" },
  { href: "/#how-it-works", label: "Missions" },
  { href: "/#journeys", label: "Workers" },
  { href: "/#evidence", label: "Evidence" },
  { href: "/supervisor", label: "Orders" },
];

const BOTTOM_NAV: NavItem[] = [
  { href: "/", label: "Site" },
  { href: "/supervisor", label: "Orders" },
  { href: "/worker", label: "My Parchi" },
  { href: "/facilitator", label: "Assistance" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const activeLink = (href: string) => {
    if (href.startsWith("/#") && pathname === "/") return true;
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <div className="site-root">
      <header className="site-header">
        <Link href="/" className="site-brand" aria-label="AADHESH home">
          <span className="brand-glyph" aria-hidden="true"><i/><i/><i/></span>
          <span>AADHESH</span>
        </Link>
        <nav className="site-nav" aria-label="Primary navigation">
          {DESKTOP_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={activeLink(item.href) ? "site-nav-link site-nav-link-active" : "site-nav-link"}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <SessionBadge />
        <Link className="header-cta" href="/supervisor">
          Open site console <span aria-hidden="true">↗</span>
        </Link>
      </header>
      <main className="site-main">{children}</main>
      <nav className="site-bottom-nav" aria-label="Role entry navigation">
        {BOTTOM_NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={activeLink(item.href) ? "site-bottom-link site-bottom-link-active" : "site-bottom-link"}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
