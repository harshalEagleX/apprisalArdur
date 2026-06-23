import type { NextConfig } from "next";

// Hosts allowed to load Next.js dev resources (HMR websocket etc.) cross-origin.
// Comma-separated, from ALLOWED_DEV_ORIGINS (init-env.sh auto-fills the LAN IP).
// e.g. ALLOWED_DEV_ORIGINS=192.168.1.148
const devOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  ...(devOrigins.length ? { allowedDevOrigins: devOrigins } : {}),
};

export default nextConfig;
