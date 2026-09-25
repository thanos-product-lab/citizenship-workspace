"use client";

import Link from "next/link";
import type { JSX } from "react";

import { useEvidence } from "../useEvidence";
import type { EvidenceItem } from "../library";
import { DocumentReview } from "./DocumentReview";

/**
 * The review screen's shell: which document this is, and a way back.
 *
 * The document's name comes from the library query the Evidence destination has already
 * loaded, so arriving here from a row is usually free. Fetching it separately would add a
 * request whose only job is a heading — and a heading is not worth a round trip when the
 * answer is already in the cache.
 */
export function ReviewDestination({
  caseId,
  evidenceItemId,
}: {
  caseId: string;
  evidenceItemId: string;
}): JSX.Element {
  const library = useEvidence(caseId);
  const items = (library.data?.items ?? []) as EvidenceItem[];
  const document = items.find((item) => item.id === evidenceItemId);

  return (
    <section className="cw-section" aria-labelledby="review-heading">
      <Link className="cw-case-header__back" href={`/cases/${caseId}/evidence`}>
        ← Back to evidence
      </Link>
      <h1 id="review-heading">Confirm what we read</h1>
      <p style={{ color: "var(--cw-text-muted)" }}>
        {document ? (
          <>
            <strong>{document.display_name}</strong>. Check each value against the
            document. Nothing counts until you confirm it, and for the values that
            matter most we ask you to type what the document says. Each answer saves
            as you go, so you can leave and come back.
          </>
        ) : (
          <>
            Check each value against the document. Nothing counts until you confirm
            it. Each answer saves as you go.
          </>
        )}
      </p>
      <DocumentReview
        caseId={caseId}
        evidenceItemId={evidenceItemId}
        documentName={document?.display_name ?? "This document"}
      />
    </section>
  );
}
