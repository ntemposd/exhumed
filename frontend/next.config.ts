// Keep Next configuration intentionally small until the frontend needs more
// environment-specific behavior.
import type { NextConfig } from "next";

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