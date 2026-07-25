import type { NextConfig } from "next";

const config: NextConfig = {
  // Workspace TypeScript packages are transpiled by Next rather than pre-built.
  transpilePackages: ["@cw/api-client", "@cw/design-system"],
};

export default config;
