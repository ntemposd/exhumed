// Keep Next configuration intentionally small until the frontend needs more
// environment-specific behavior.
import type { NextConfig } from "next";

if (process.env.NODE_ENV === "production" && !process.env.BACKEND_URL?.trim()) {
  throw new Error(
    "BACKEND_URL is required for production builds. Set it in the frontend host environment (for example Vercel project settings).",
  );
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  webpack: (config, { dev }) => {
    if (dev) {
      config.cache = false;
    }

    return config;
  },
};

export default nextConfig;