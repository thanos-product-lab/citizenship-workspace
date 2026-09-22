"use client";

import {
  StatusGlyph,
  evidenceProcessingTokens,
  toEvidenceProcessingState,
} from "@cw/design-system";
import Link from "next/link";
import type { JSX } from "react";

import { stateNote, TERMINAL_PROCESSING_STATES, type EvidenceItem } from "./library";

/** The id the destination moves focus to once an upload lands. */
export const UPLOAD_PROGRESS_ID = "upload-progress";

/**
 * What happened to the document just uploaded, visible and staying on screen.
 *
 * Before this, success was a sentence in a visually hidden live region. A sighted user saw
 * the form reset and nothing else, and had to find the new row to learn whether it worked.
 * The live region stays; this is its visible equivalent, and it keeps following the
 * document while the worker reads it.
 *
 * **Steps reached, never steps ahead.** The library deliberately draws no track through
 * the processing states, because a document's route is not fixed: it can stop at
 * Unsupported, at No text found or at Failed, as well as arriving at Needs your
 * confirmation. So this lists only what has already happened. The last step is drawn
 * once there is one, and it is the real outcome, so "Ready to review" appears only for a
 * document that is. Until then, one sentence says what reading may lead to, which is a
 * statement rather than a stage.
 */
export function UploadProgress({
  caseId,
  displayName,
  item,
}: {
  caseId: string;
  displayName: string;
  /** Undefined for the moment between the upload landing and the library refetching. */
  item: EvidenceItem | undefined;
}): JSX.Element {
  const status = item?.processing_status;
  const finished = status !== undefined && TERMINAL_PROCESSING_STATES.has(status);
  const outcome = finished ? toEvidenceProcessingState(status) : null;
  const ready = status === "AWAITING_CONFIRMATION";

  return (
    <section
      id={UPLOAD_PROGRESS_ID}
      // Programmatic focus only. The form that was just submitted collapses on success,
      // and without somewhere to land a keyboard user would be dropped to <body>.
      tabIndex={-1}
      className="cw-upload-progress"
      aria-labelledby={`${UPLOAD_PROGRESS_ID}-heading`}
    >
      <h3 id={`${UPLOAD_PROGRESS_ID}-heading`} className="cw-upload-progress__heading">
        {displayName}
      </h3>

      <ol className="cw-upload-progress__steps">
        <li data-step="done">
          <StatusGlyph name="check" size={14} />
          <span>Uploaded</span>
        </li>
        <li data-step={finished ? "done" : "current"}>
          <StatusGlyph name={finished ? "check" : "clock"} size={14} />
          <span>{finished ? "Document read" : "Reading document…"}</span>
        </li>
        {outcome ? (
          <li data-step="outcome">
            <StatusGlyph name={evidenceProcessingTokens[outcome].glyph} size={14} />
            <span>{ready ? "Ready to review" : evidenceProcessingTokens[outcome].label}</span>
          </li>
        ) : null}
      </ol>

      {!finished ? (
        <p className="cw-upload-progress__note">
          If it finds values like travel dates, they will be ready for you to review here.
          You can leave this page; reading carries on.
        </p>
      ) : ready && item ? (
        <p className="cw-upload-progress__note">
          <Link className="cw-button" href={`/cases/${caseId}/evidence/${item.id}/review`}>
            Review extracted information
          </Link>
        </p>
      ) : item && stateNote(item) ? (
        <p className="cw-upload-progress__note">{stateNote(item)}</p>
      ) : null}
    </section>
  );
}
