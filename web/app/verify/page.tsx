"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiErrorNote, Button, IconTerminal, Loading, Panel, Pill } from "@/components/ui";
import { getJson, failureOf, type ApiFailure } from "@/lib/api";
import type { VerifyPayload } from "@/lib/types";

export default function VerifyPage() {
  const [data, setData] = useState<VerifyPayload | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await getJson<VerifyPayload>("/api/verify"));
    } catch (err) {
      setError(failureOf(err));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void run();
  }, [run]);

  return (
    <div className="mx-auto max-w-4xl px-5 py-8 lg:px-10 lg:py-10">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <div className="label">Verification — the centrepiece</div>
          <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight">
            Re-prove every citation against hashed source bytes
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-dim">
            Zero infrastructure, seconds to run. A quote is only counted as proved if the document
            it was extracted from still hashes to the manifest — extracted text is a cache of what
            a document said.
          </p>
        </div>
        <Button onClick={run} disabled={busy} variant="secondary">
          <IconTerminal className="h-4 w-4" />
          {busy ? "Running…" : "Run verification"}
        </Button>
      </header>

      {error && (
        <div className="mt-5">
          <ApiErrorNote error={error} />
        </div>
      )}
      {!data && !error && <Loading label="Re-proving the corpus" />}

      {data && (
        <div className="mt-6 space-y-6">
          <ResultPanel
            command={data.verify.command}
            output={data.verify.output}
            state={data.verify.passed ? "pass" : "fail"}
            exitCode={data.verify.exit_code}
            headline={data.verify.passed ? "PASS" : "FAIL"}
            caption="Every cited quote was found verbatim on the page it claims."
          />

          <ResultPanel
            command={data.tamper.command}
            output={data.tamper.output}
            state={data.tamper.caught ? "caught" : "miss"}
            exitCode={data.tamper.exit_code}
            headline={data.tamper.caught ? "FAILED (expected)" : "NOT DETECTED"}
            caption="One byte is flipped in a scratch copy. Verification must fail — the failure is the proof. A hash check that has never failed proves only that you did not delete your files."
          />

          <p className="text-xs leading-relaxed text-faint">
            Note: <span className="data">make verify --tamper</span> is not valid GNU make syntax —
            make parses <span className="data">--tamper</span> as one of its own options. The
            tamper target is <span className="data">make verify-tamper</span>, which is what ran
            above (via <span className="data">python -m aadesh_cli.verify --tamper</span>).
          </p>
        </div>
      )}
    </div>
  );
}

function ResultPanel({
  command,
  output,
  state,
  exitCode,
  headline,
  caption,
}: {
  command: string;
  output: string;
  state: "pass" | "fail" | "caught" | "miss";
  exitCode: number;
  headline: string;
  caption: string;
}) {
  const tone = state === "pass" ? "ok" : state === "caught" ? "warn" : "danger";
  return (
    <Panel
      title={<span className="data text-sm">{command}</span>}
      actions={
        <div className="flex items-center gap-2">
          <Pill tone={tone}>{headline}</Pill>
          <span className="data text-[12px] text-faint">exit {exitCode}</span>
        </div>
      }
    >
      <p className="mb-3 text-sm text-dim">{caption}</p>
      <pre className="data max-h-72 overflow-auto whitespace-pre-wrap border border-line bg-black/40 p-3 text-[12px] leading-relaxed text-dim">
        {output}
      </pre>
    </Panel>
  );
}
