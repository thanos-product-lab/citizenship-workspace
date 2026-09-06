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
 * **When the origin is unset in production this warns and falls back to `'self'`,
 * rather than failing the build.**
 *
 * It did fail the build for one afternoon, on the reasoning `check_backing_services`
 * uses on the API side: refuse to start rather than start wrong. That reasoning does not
 * transfer, and two blocked deploys are what showed it. `STORAGE_ENDPOINT_URL` is
 * boot-blocking because without it the *feature* is pointed at a host that is not there.
 * This variable is a bound on something that had no bound at all the day before, so its
 * absence cannot leave the product worse than it already was — and taking every page of
 * the app down for a missing defence-in-depth header is a trade nobody would make on
 * purpose.
 *
 * `'self'` and not "omit `frame-src`": omitting it permits every origin, which is the one
 * outcome worse than a broken preview. This fails **closed** — the frame is refused, the
 * rest of the app is untouched, and the Text pane beside it still shows the document's
 * words, so the review interaction survives with its accessible half.
 *
 * The warning is the part that has to carry the weight now, so it says what broke, what
 * to set, and where to read the value.
 */
const FRAME_ORIGIN = (() => {
  const configured = process.env["NEXT_PUBLIC_STORAGE_ORIGIN"];
  if (configured) return configured;
  if (process.env.NODE_ENV !== "production") return "http://localhost:9000";

  console.warn(
    [
      "",
      "  ⚠  NEXT_PUBLIC_STORAGE_ORIGIN is unset.",
      "     Falling back to frame-src 'self', so the document preview on the review",
      "     screen will not render. Everything else works, and the Text pane beside it",
      "     still shows what was read out of the document.",
      "",
      "     Set it to the scheme and host of the URLs the API *signs* — which is not",
      "     necessarily STORAGE_ENDPOINT_URL. boto3 uses virtual-hosted addressing for a",
      "     DNS-compatible bucket, so an endpoint of https://s3.eu-west-2.amazonaws.com",
      "     signs https://your-bucket.s3.eu-west-2.amazonaws.com.",
      "",
      "     Read it off a real URL rather than deriving it: call",
      "     GET /api/v1/cases/{case_id}/evidence/{id}/content on the deployed API and",
      "     take the origin of the `url` it returns. docs/DEPLOYMENT.md section B.",
      "",
    ].join("\n"),
  );
  // `'self'`, never omitted. Omitting `frame-src` permits every origin, which is the one
  // outcome worse than a preview that does not load.
  return "'self'";
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
              // `'self'` twice when the origin is unset is harmless and keeps the
              // fallback a one-token change rather than a second code path.
              `frame-src 'self' ${FRAME_ORIGIN}`,
              "object-src 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default config;
