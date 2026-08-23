"use client";

import { type JSX, useRef, useState } from "react";

import { EvidenceState } from "@cw/design-system";

import { cardStyle, errorTextStyle, secondaryButtonStyle } from "@/components/ui";


import { CATEGORY_LABELS, formatBytes, type EvidenceItem } from "./library";
import { UploadDocument } from "./UploadDocument";
import { useEvidence } from "./useEvidence";

/**
 * The Evidence destination: the documents this case holds, and what has been done to them.
 *
 * Three decisions worth stating.
 *
 * **This is not a file manager.** UI/UX §9.1 asks each document to show how it contributes
 * to the case — what it supports, what was extracted, what needs confirming. In slice 1
 * none of that exists yet, and the honest version of that table is a column that says so
 * rather than one that is blank. "Not yet read by anything" is a true statement about a
 * stored document; an empty "Supports" cell would read as "supports nothing", which is a
 * stronger claim than the product has earned.
 *
 * **An empty library is a real statement**, so a failed fetch must never render as one —
 * the same rule the issue queue follows. Silence and "you have uploaded nothing" must not
 * look alike.
 *
 * **No progress bar over the processing states.** A document's route through Domain §14.4
 * is not a fixed pipeline, and `AWAITING_CONFIRMATION` has no producer until M8. A stepper
 * would draw stages this build cannot reach.
 */
export function EvidenceDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data, status, refetch, isFetching } = useEvidence(caseId);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [announcement, setAnnouncement] = useState("");

  return (
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" ref={headingRef} tabIndex={-1} className="cw-case-data__heading">
        Evidence
      </h2>
      <p className="cw-case-data__note">
        Documents you have uploaded to support this case. Nothing here has been read or
        checked yet, so every figure in your assessment still rests on dates you entered
        yourself.
      </p>

      <div aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </div>

      {status === "pending" ? (
        <p role="status" style={{ color: "var(--cw-text-muted)" }}>
          Loading your documents…
        </p>
      ) : null}

      {status === "error" ? (
        <div role="alert" style={{ ...cardStyle, display: "grid", gap: "var(--cw-space-3)" }}>
          <p style={{ margin: 0, ...errorTextStyle }}>
            Your documents could not be loaded, so this list is not a statement about what
            the case holds.
          </p>
          <div>
            <button type="button" style={secondaryButtonStyle} onClick={() => void refetch()}>
              Try again
            </button>
          </div>
        </div>
      ) : null}

      {status === "success" ? (
        <>
          <UploadDocument
            caseId={caseId}
            supportedMediaTypes={data.supported_media_types ?? []}
            maxBytes={data.max_upload_bytes}
            onUploaded={(name) => setAnnouncement(`${name} uploaded.`)}
          />

          {data.items.length === 0 ? (
            <p style={{ color: "var(--cw-text-muted)" }} data-testid="evidence-empty">
              No documents yet. Uploading one stores it privately against this case.
            </p>
          ) : (
            <EvidenceTable items={data.items as EvidenceItem[]} busy={isFetching} />
          )}
        </>
      ) : null}
    </section>
  );
}

function EvidenceTable({ items, busy }: { items: EvidenceItem[]; busy: boolean }): JSX.Element {
  return (
    <div className="cw-trips-wrap">
      <table className="cw-trips" aria-busy={busy || undefined}>
        <caption className="cw-trips__caption">
          Documents uploaded to this case, newest first. Nothing has read them yet.
        </caption>
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">Type</th>
            <th scope="col">State</th>
            <th scope="col">Size</th>
            <th scope="col">Added</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <th scope="row" className="cw-trips__destination">
                {item.display_name}
                {item.original_filename ? (
                  <span
                    style={{
                      display: "block",
                      color: "var(--cw-text-muted)",
                      fontSize: "var(--cw-text-xs)",
                      fontWeight: "var(--cw-weight-regular)",
                    }}
                  >
                    {item.original_filename}
                  </span>
                ) : null}
              </th>
              <td>{CATEGORY_LABELS[item.category] ?? item.category}</td>
              <td>
                <EvidenceState status={item.processing_status} size="sm" withMeaning />
              </td>
              <td>{formatBytes(item.size_bytes)}</td>
              <td>{formatDate(item.uploaded_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A date, in the form the timeline already uses. */
function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
