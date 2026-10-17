import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Uploads to the document vault go through server actions and the proxy. Files can be
    // up to 20 MB; the extra room is for the form's own overhead.
    serverActions: { bodySizeLimit: "21mb" },
    proxyClientMaxBodySize: "21mb",
  },
};

export default nextConfig;
