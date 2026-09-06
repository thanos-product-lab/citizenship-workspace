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
 *
 * **The origin must be set when deployed.** Defaulting to localhost and shipping is
 * the failure this repository has already had twice: M7's presigned URLs were signed for a host the browser could not resolve, and
 * M8's compose stack ran with no provider key. Both were green locally and dead
 * deployed, and both were silent. This one would be too — a CSP naming the wrong origin
 * does not error, it shows an empty frame where the user's document should be, on the
 * screen whose entire task is reading that document.
 *
 * So it fails the *build* rather than the request, which is the discipline
 * `check_backing_services` already applies on the API side: refuse to start rather than
 * start wrong.
 */
const STORAGE_ORIGIN = (() => {
  const configured = process.env["NEXT_PUBLIC_STORAGE_ORIGIN"];
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXT_PUBLIC_STORAGE_ORIGIN is unset. It is the only origin this app may frame, " +
        "and the document preview shows an empty frame without it. Set it to the " +
        "browser-facing address of the object store — the same address the API signs " +
        "URLs against (STORAGE_PUBLIC_ENDPOINT_URL, or the S3 endpoint when unset).",
    );
  }
  return "http://localhost:9000";
})();

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
