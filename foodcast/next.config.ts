import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  experimental: {
    turbopackFileSystemCacheForDev: true,
  },
  images: {
    domains: ["pub-86f4b5249e5c4021bb05d46908eeb094.r2.dev"],
  },
};

export default nextConfig;
