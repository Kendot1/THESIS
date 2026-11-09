import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Isolate only the dedicated local rolling preview; normal dev/build unchanged.
  distDir: process.env.FOODCAST_LOCAL_RESEARCH === "rolling-research" ? ".next-rolling-research" : ".next",
  reactCompiler: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts", "@base-ui/react"],
  },
  images: {
    dangerouslyAllowSVG: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "pub-86f4b5249e5c4021bb05d46908eeb094.r2.dev",
        port: "",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "**",
      },
      {
        protocol: "http",
        hostname: "**",
      },
    ],
  },
};

export default nextConfig;
