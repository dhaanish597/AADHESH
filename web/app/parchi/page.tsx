"use client";

import { useEffect } from "react";

/**
 * The legacy Parchi path.
 *
 * A Parchi is opened from the QR link a worker scans, which is `/worker#payload=<token>` -- the
 * token is in the fragment, so it never reaches a server and never appears in a request log.
 * This route exists only for links shaped `/parchi/...`, and it redirects rather than rendering
 * anything of its own.
 *
 * It is a client component on purpose: the console is a static export with no server, so a
 * build-time redirect has nowhere to run. The effect redirects as soon as the page is live.
 */
export default function ParchiRedirectPage() {
  useEffect(() => {
    window.location.replace("/worker");
  }, []);
  return null;
}
