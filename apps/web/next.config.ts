import type { NextConfig } from "next";

/**
 * Where the browser is allowed to fetch from, and — from M8 slice 3b — what it is
 * allowed to put in a frame.
 *
 * Until that slice this app framed nothing. It now embeds a user's own uploaded document
 * from the object store so they can read it while confirming what a model read out of it,
 * which means remote, user-supplied bytes render inside a page carrying their session.
 * A `frame-src` allowlist is what bounds that to the one origin meant to be framed: a
 * signed URL pointing anywhere else, however it got there, does not load.
 *
 * `object-src 'none'` goes with it. `<object>`/`<embed>` are the other way to get a
 * plugin to interpret bytes, and nothing in this product uses them.
 *
 * **What this does not fix**, and the reason it is worth saying here rather than only in
 * the ADR: a hostile PDF's own JavaScript still runs in Chrome's PDF viewer. `sandbox` on
 * the iframe would stop it and also stops the viewer rendering at all — measured, every
 * token combination — so the preview would cease to exist for the product's primary
 * document type. The frame is cross-origin, so that script cannot reach this app's DOM or
 * its Clerk token; what it can do is put attacker-chosen text in front of someone inside
 * their own workspace. Recorded in `docs/security/`, and the durable fix is PDF.js with
 * scripting disabled — already on the approved stack list, and a slice of work rather
 * than a config line.
 *
 * Deliberately not a full CSP: `script-src` needs a nonce strategy that Next's inline
 * bootstrap and Clerk both have opinions about, and shipping a broken one is worse than
 * shipping this one honestly scoped. This is the directive the new surface needs.
 */
const STORAGE_ORIGIN =
  process.env["NEXT_PUBLIC_STORAGE_ORIGIN"] ?? "http://localhost:9000";

const config: NextConfig = {
  // Workspace TypeScript packages are transpiled by Next rather than pre-built.
  transpilePackages: ["@cw/api-client", "@cw/design-system"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              `frame-src 'self' ${STORAGE_ORIGIN}`,
              "object-src 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default config;
