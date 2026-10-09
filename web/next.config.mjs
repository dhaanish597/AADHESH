/** @type {import('next').NextConfig} */

// The frontend never imports the deterministic core directly. It talks to the local JSON API
// (`make api`), which is itself a thin adapter over `aadesh_core`. Proxying keeps the browser
// same-origin, so there is no CORS surface and no second source of truth.
const API = process.env.AADESH_API_URL ?? "http://127.0.0.1:8787";

const nextConfig = {
  // This repo has more than one lockfile; pin the tracing root to the web app. Scoped here so
  // Next does not stray into the parent workspace when collecting build traces.
  outputFileTracingRoot: process.cwd(),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  experimental: {
    // Keep dev builds fast: don't eagerly transpile all 9000+ Phosphor modules.
    optimizePackageImports: ["@phosphor-icons/react"],
  },
};

export default nextConfig;
