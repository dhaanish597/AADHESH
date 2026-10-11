import path from "node:path";

/** @type {import('next').NextConfig} */

// The frontend never imports the deterministic core directly. It talks to an HTTP API, which is
// itself a thin adapter over `aadesh_core`. Two ways of reaching it, and the environment picks:
//
//   * LOCAL (`make web`): `/api/*` is proxied to the local JSON API on 8787. Proxying keeps the
//     browser same-origin, so there is no CORS surface and no second source of truth.
//   * DEPLOYED (`AADHESH_STATIC_EXPORT=1`): Amplify Hosting serves static files, so there is no
//     server to proxy with. The console calls API Gateway directly, using
//     `NEXT_PUBLIC_API_BASE_URL`, and API Gateway carries the CORS policy naming this origin.
//     `rewrites` is omitted in that mode because a static export has no server to apply it -- a
//     rewrite that silently does nothing would be worse than none.
const API = process.env.AADESH_API_URL ?? "http://127.0.0.1:8787";
const STATIC_EXPORT = process.env.AADHESH_STATIC_EXPORT === "1";
const REPO_ROOT = path.resolve(process.cwd(), "..");

const nextConfig = {
  // Root both Turbopack resolution and file tracing at the repo because the web app imports two
  // small source manifests from sibling directories.
  outputFileTracingRoot: REPO_ROOT,
  // The UI reads the authoritative manifest and Cedar denial copy from the repo root.
  // Next 16/Turbopack otherwise treats those valid sibling imports as outside its root.
  turbopack: { root: REPO_ROOT },
  // Allow isolated local verification builds while the normal .next dev server is running.
  distDir: process.env.AADHESH_NEXT_DIST_DIR ?? ".next",
  ...(STATIC_EXPORT
    ? {
        output: "export",
        // One directory per route, so `/worker` resolves to `/worker/index.html` on a plain
        // static host -- which is what makes a scanned QR link work.
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
        },
      }),
};

export default nextConfig;
