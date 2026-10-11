import manifest from "../../../corpus/sources/manifest.json";
import Link from "next/link";

export default function EvidencePage() {
  return (
    <div className="evidence-ledger mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="flex flex-wrap items-end justify-between gap-5 border-b border-line pb-5">
        <div>
          <div className="label">Evidence explorer · official source register</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Follow each decision to its source.</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-dim">Inspect the cited CAQM documents and their recorded provenance. The Stage III invocation below is historical and was revoked on 22 January 2026.</p>
        </div>
        <Link className="action-primary" href="/verify">Run source verification</Link>
      </header>
      <div className="mt-6 space-y-4">
        {manifest.documents.map((document) => (
          <article key={document.doc_id} className="console-panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div><span className="label">{document.publisher}</span><h2 className="mt-2 text-lg font-semibold">{document.title}</h2></div>
              <span className="data text-xs text-dim">{Object.keys(document.page_sha256).length} pages</span>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <div><dt className="label">Retrieved</dt><dd className="data mt-1 text-xs">{document.retrieved_at}</dd></div>
            </dl>
            <div className="mt-4 flex flex-wrap items-center gap-5 text-sm">
              <a href={document.source_url} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-4">Open official source PDF</a>
              <details className="text-xs text-faint">
                <summary className="min-h-11 cursor-pointer py-3">Technical provenance</summary>
                <dl className="grid gap-2 border-t border-line pt-3">
                  <div><dt className="label">Source record</dt><dd className="data mt-1">{document.doc_id}</dd></div>
                  <div><dt className="label">SHA-256</dt><dd className="data mt-1 break-all">{document.sha256}</dd></div>
                  <div><dt className="label">Retrieved bytes</dt><dd className="data mt-1">{document.byte_size.toLocaleString()}</dd></div>
                </dl>
              </details>
            </div>
          </article>
        ))}
      </div>
      <section className="mt-8 evidence-console">
        <div className="label">Verification terminal · recorded local run</div>
        <pre className="verification-output">{`$ make verify\nVERIFIED — 3 source objects and 55 citations re-proved against indexed source bytes.\n\n$ make verify-tamper\nFAIL — one byte changed in an isolated scratch copy; manifest hash mismatch detected.\nFAILED (expected) — the tampered byte was detected. The citation gate works.`}</pre>
      </section>
    </div>
  );
}
