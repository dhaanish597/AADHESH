import Link from "next/link";

const NAV = [
  { href: "/#system-map", label: "Product" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#evidence", label: "Evidence" },
  { href: "/#journeys", label: "Worker impact" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="site-root">
      <header className="site-header">
        <Link href="/" className="site-brand" aria-label="AADHESH home">
          <span className="brand-glyph" aria-hidden="true"><i/><i/><i/></span>
          <span>AADHESH</span>
        </Link>
        <nav className="site-nav" aria-label="Primary navigation">
          {NAV.map((item) => <Link key={item.href} href={item.href}>{item.label}</Link>)}
        </nav>
        <Link className="header-cta" href="/supervisor">Open site console <span aria-hidden="true">↗</span></Link>
      </header>
      <main className="site-main">{children}</main>
    </div>
  );
}
