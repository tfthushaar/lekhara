import type { NextConfig } from "next";

const production = process.env.NODE_ENV === "production";
// Served over HTTPS: in production, unless LEKHARA_HTTPS=0 (a production build run locally).
const https = production && process.env.LEKHARA_HTTPS !== "0";

// The Content Security Policy. Scripts may be inline because the prerendered shells stream
// inline scripts and nonces are incompatible with Partial Prerendering (see the Next.js CSP
// guide); everything else is held to this site. Documents open in a frame on the document
// page, so frames are allowed from this site and no other.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self'",
  ...(https ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Data room links carry their key in the address: never send it to another site.
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ...(https ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  experimental: {
    // Uploads to the document vault go through server actions and the proxy. Files can be
    // up to 20 MB; the extra room is for the form's own overhead.
    serverActions: { bodySizeLimit: "21mb" },
    proxyClientMaxBodySize: "21mb",
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
