import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // "/" is the landing page of every role (app/(app)/page.tsx), no longer a redirect to /import
};

export default nextConfig;
