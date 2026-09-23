"use client";

import type { components } from "@cw/api-client";
import { Skeleton } from "@cw/design-system";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { JSX, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { RouteOnboarding } from "@/features/onboarding/RouteOnboarding";
import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

import { CaseHeader } from "./CaseHeader";
import { MAIN_LANDMARK_ID } from "./destinations";
import { DeleteCaseControl } from "./DeleteCaseControl";

type Case = components["schemas"]["CaseResponse"];

/**
 * The page content, in the readable column every band of the shell shares.
 *
 * Owns the `<main>` landmark, so it wraps the destination's content and *not* the case
 * header — a persistent header is context, and "skip to main content" should skip it.
 * Every lifecycle branch below renders through here, so a not-found and a full workspace
 * sit on the same column and the landmark exists on every path rather than only the happy
 * one.
 *
 * `tabIndex={-1}` so the skip link can move focus here. Without it the browser scrolls to
 * the landmark and leaves focus at the top of the document, so the next Tab returns to the
 * navigation the user just asked to skip — the classic half-working skip link.
 */
function ContentShell({ children }: { children: ReactNode }): JSX.Element {
  return (
    <main className="cw-shell__main" id={MAIN_LANDMARK_ID} tabIndex={-1}>
      <div className="cw-shell__inner">{children}</div>
    </main>
  );
}

/** How long a load may take before the skeleton appears. Faster loads show nothing, rather
 *  than a frame of grey shapes that is gone before it can be read. */
export const SKELETON_DELAY_MS = 300;

/**
 * The case shell while the case loads: the identity band, the navigation row and a content
 * block as placeholder shapes, laid out with the real shell's classes so the page does not
 * move when the case arrives.
 *
 * Screen readers get the sentence and not the shapes, which are all `aria-hidden`. The
 * sentence is there from the first frame; only the shapes wait for `SKELETON_DELAY_MS`.
 */
function CaseShellSkeleton(): JSX.Element {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <div className="cw-case-shell" aria-hidden="true" data-testid="case-shell-skeleton">
        {visible ? (
          <>
            <div className="cw-case-shell__identity">
              <div className="cw-shell__inner">
                {/* The real header's own row classes, with shapes the size of what fills
                    them (the 28px avatar, the 42px Update assessment button, two lines of
                    details), so the navigation row starts where it will stay. */}
                <div className="cw-case-header__top">
                  <Skeleton width="6rem" height="0.875rem" />
                  <Skeleton width="1.75rem" height="1.75rem" round />
                </div>
                <div className="cw-case-header__identity">
                  <Skeleton width="min(20rem, 55%)" height="1.75rem" />
                  <Skeleton width="10.5rem" height="2.625rem" style={{ marginLeft: "auto" }} />
                </div>
                <div className="cw-case-header__facts cw-shell-skeleton__facts">
                  <Skeleton width="min(26rem, 90%)" height="0.875rem" />
                  <Skeleton width="10rem" height="0.875rem" />
                </div>
              </div>
            </div>
            <div className="cw-case-shell__nav">
              <div className="cw-shell__inner cw-shell-skeleton__nav">
                {[4.5, 4, 6, 4.5, 3.5, 5].map((rem, index) => (
                  <Skeleton key={index} width={`${rem}rem`} height="0.875rem" />
                ))}
              </div>
            </div>
          </>
        ) : null}
      </div>
      <ContentShell>
        <p role="status" className="cw-visually-hidden">
          Loading this case…
        </p>
        {visible ? (
          <div className="cw-shell-skeleton__stack" aria-hidden="true">
            <Skeleton width="12rem" height="1.25rem" />
            <Skeleton height="6rem" />
            <Skeleton height="6rem" />
          </div>
        ) : null}
      </ContentShell>
    </>
  );
}

/**
 * Everything every case destination shares: the case fetch, the lifecycle branch, and the
 * persistent header and navigation.
 *
 * This is mounted from the route **layout**, not from each page, so the header and
 * navigation survive a move between destinations rather than remounting. A remount would
 * reset scroll and drop keyboard focus to `<body>` on every navigation — the workspace
 * would technically work and feel broken.
 *
 * The lifecycle branch decides whether there is a workspace at all:
 *
 * - `DRAFT` — route onboarding, and **no navigation**. There are no assessments, no
 *   requirements and no travel history yet, so three destinations would offer two empty
 *   rooms and compete with the one question onboarding is asking.
 * - `ACTIVE` — header, navigation, and the destination's own page.
 * - `DELETION_PENDING` — a terminal notice. No destination is reachable.
 *
 * A not-found and an unowned case are one state, because the server deliberately makes
 * them indistinguishable.
 */
export function CaseChrome({
  caseId,
  children,
}: {
  caseId: string;
  children: ReactNode;
}): JSX.Element {
  const api = useApiClient();
  const client = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);

  const {
    data: caseData,
    status,
    error,
    refetch,
  } = useQuery({
    queryKey: caseKeys.case(caseId),
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/cases/{case_id}", {
        params: { path: { case_id: caseId } },
      });
      if (!data) {
        throw Object.assign(new Error("case unavailable"), { status: response?.status ?? 0 });
      }
      return data;
    },
  });

  const notFound = (error as { status?: number } | null)?.status === 404;

  // Move focus to the case heading when a user action transitions the case into
  // deletion-pending, so the confirm button that unmounts doesn't drop focus to <body>.
  // Guarded so opening an already-pending case on load doesn't steal focus.
  const prevLifecycle = useRef<string | null>(null);
  useEffect(() => {
    const lifecycle = caseData?.lifecycle_status ?? null;
    if (lifecycle === "DELETION_PENDING" && prevLifecycle.current !== null) {
      headingRef.current?.focus();
    }
    prevLifecycle.current = lifecycle;
  }, [caseData?.lifecycle_status]);

  if (status === "pending") {
    return <CaseShellSkeleton />;
  }

  if (notFound) {
    return (
      <ContentShell>
        <h1 style={{ fontSize: "var(--cw-text-2xl)" }}>Case not found</h1>
        <p style={{ color: "var(--cw-text-muted)" }}>
          This case doesn’t exist, or it isn’t yours. <a href="/">Back to your cases</a>.
        </p>
      </ContentShell>
    );
  }

  if (status === "error" || !caseData) {
    return (
      <ContentShell>
        <div role="alert">
          <p style={{ color: "var(--cw-status-not-satisfied)" }}>We couldn’t load this case.</p>
          <button type="button" onClick={() => void refetch()} className="cw-button">
            Try again
          </button>
        </div>
      </ContentShell>
    );
  }

  if (caseData.lifecycle_status === "DELETION_PENDING") {
    return (
      <ContentShell>
        <a className="cw-case-header__back" href="/">
          <span aria-hidden="true">←</span> Your cases
        </a>
        <h1 className="cw-case-header__title" ref={headingRef} tabIndex={-1}>
          {caseData.title}
        </h1>
        <p role="status" style={{ marginTop: "var(--cw-space-4)", color: "var(--cw-text-muted)" }}>
          This case is scheduled for deletion. It can no longer be edited.
        </p>
      </ContentShell>
    );
  }

  if (caseData.lifecycle_status !== "ACTIVE") {
    return (
      <ContentShell>
        <a className="cw-case-header__back" href="/">
          <span aria-hidden="true">←</span> Your cases
        </a>
        <h1 className="cw-case-header__title" ref={headingRef} tabIndex={-1}>
          {caseData.title}
        </h1>
        <RouteOnboarding caseId={caseId} />
        {/* Deletion normally lives under Case data, but a draft case has no destinations.
            Abandoning it is then the only case-level action available, so it stays here. */}
        <DeleteCaseControl
          caseId={caseId}
          onDeleted={(updated: Case) => client.setQueryData(caseKeys.case(caseId), updated)}
        />
      </ContentShell>
    );
  }

  return (
    <>
      <CaseHeader caseData={caseData} headingRef={headingRef} />
      <ContentShell>{children}</ContentShell>
    </>
  );
}
