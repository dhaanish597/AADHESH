const tokens = [
  ["Concrete 900", "#13161a", "Console foundation"],
  ["Concrete 800", "#1b1f25", "Instrument panels"],
  ["Steel 100", "#eef1f4", "Primary console text"],
  ["Caution", "#ffb000", "Invoked or armed state"],
  ["Halt", "#e5332a", "Stopped state"],
  ["Evidence", "#4a7cf0", "Focus and provenance"],
  ["Paper", "#f6f1e4", "Worker parchi"],
  ["Stamp blue", "#1f3a93", "Paper artifact ink"],
];

export default function StyleguidePage() {
  return (
    <div className="mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="border-b border-line pb-5"><div className="label">Design system · Field Instrument</div><h1 className="mt-2 text-3xl font-semibold">Operational by default. Evidence in view.</h1><p className="mt-3 max-w-2xl text-sm text-dim">Cool concrete frames the supervisor console; warm paper carries the worker’s record. Signal colours always communicate state.</p></header>
      <section className="mt-7"><h2 className="label">Colour register</h2><div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{tokens.map(([name, color, purpose]) => <article key={name} className="console-panel p-3"><div style={{ backgroundColor: color }} className="h-16 border border-line"/><strong className="mt-3 block">{name}</strong><code className="data text-xs">{color}</code><p className="mt-1 text-xs text-dim">{purpose}</p></article>)}</div></section>
      <section className="mt-8"><h2 className="label">Typography and state</h2><div className="mt-3 grid gap-4 lg:grid-cols-2"><div className="console-panel p-5"><p className="label">Mono · tabular data</p><p className="data mt-3 text-3xl">34 / 34</p><p className="provenance-line">16 Jan 2026 · sha256 35813475</p><div className="state-banner mt-4" data-state="caution"><h2>STAGE III REPLAY — REVOKED</h2></div></div><div className="parchi-card p-5"><span className="stamp">REPLAY RECORD</span><h2 lang="hi" className="mt-4 text-3xl font-semibold">यह 16 जनवरी की ऐतिहासिक पर्ची है।</h2><p className="mt-3">आपका काम आज बंद है</p><button className="action-primary mt-4">पर्ची स्वीकार करें</button></div></div></section>
    </div>
  );
}
