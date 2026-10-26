import type { NextConfig } from "next";

const backend = process.env.CHAT_KIT_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Allow an isolated verification server alongside the user's existing dev server.
  distDir: process.env.CHAT_KIT_NEXT_DIST_DIR ?? ".next",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
