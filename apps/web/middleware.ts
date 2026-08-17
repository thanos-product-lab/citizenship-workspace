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
     * Every path except Next internals and real static files.
     *
     * The obvious pattern — `/((?!_next|.*\..*).*)`  — excludes any path containing a
     * dot, on the assumption that a dot means a file extension. It does not: requirement
     * keys are dotted (`residence.total_absences`), so
     * `/cases/{id}/requirements/residence.total_absences` skipped the middleware entirely
     * and rendered the authenticated shell to anonymous visitors. No data leaked — the
     * API answers 401 regardless — but the route was outside `auth.protect()`, and so was
     * any future route with a dot in a parameter.
     *
     * So exclude *known static extensions* rather than "anything with a dot". `js(?!on)`
     * keeps `.json` protected while excluding `.js`.
     */
    "/((?!_next/|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ico|ttf|woff2?|txt|xml|webmanifest)$).*)",
    "/",
  ],
};
