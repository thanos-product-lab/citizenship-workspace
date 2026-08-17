import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Everything except the sign-in route requires an authenticated session.
const isPublicRoute = createRouteMatcher(["/sign-in(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    /*
     * Two entries, and the second is the one that matters.
     *
     * The first excludes Next internals and real static files so assets are not put
     * through auth. It is a heuristic on the *path*, and a path contains
     * attacker-controlled segments — which is how this went wrong twice:
     *
     *   1. `/((?!_next|.*\..*).*)` excluded any path containing a dot, on the assumption
     *      a dot means a file extension. Requirement keys are dotted
     *      (`residence.total_absences`), so every requirement detail page skipped
     *      `auth.protect()`.
     *   2. Narrowing that to known extensions fixed the dotted keys but not the class:
     *      `/cases/{id}.png` and `/cases/{id}/requirements/foo.png` still matched the
     *      exclusion, because an attacker can simply append one.
     *
     * So the app's own routes are matched **unconditionally** by the second entry. A
     * suffix cannot argue its way out of a positive match, and the static heuristic is
     * left to do only what it is safe for: excluding paths that are not app routes.
     * Add a prefix here whenever a new authenticated route tree is introduced.
     */
    "/((?!_next/|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|avif|png|gif|svg|ico|ttf|woff2?|txt|xml|map|webmanifest)$).*)",
    "/",
    "/cases/:path*",
  ],
};
