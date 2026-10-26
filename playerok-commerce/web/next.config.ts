import type { NextConfig } from "next";

// The panel talks to the FastAPI backend through this same origin: /api/* is
// rewritten to BACKEND_URL, so the session cookie stays first-party and no CORS
// is needed. The backend (API, bot, worker) runs on its own server.
const backend = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// Rewrites are fixed at build time: a Vercel build without a public HTTPS backend
// would ship a panel that silently talks to localhost, so fail the build instead.
if (process.env.VERCEL && !backend.startsWith("https://")) {
  throw new Error("BACKEND_URL must be set to the public https:// address of the API (Vercel → Settings → Environment Variables)");
}

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-Robots-Tag", value: "noindex, nofollow" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // self-hosted Docker image (web/Dockerfile) sets NEXT_OUTPUT=standalone; Vercel builds as usual
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
