"use client";

import { StatusGlyph } from "@cw/design-system";
import type { JSX } from "react";

/** The id the destination moves focus to once an upload lands. */
export const UPLOAD_PROGRESS_ID = "upload-progress";

/**
 * The document just uploaded, visible while it is being read.
 *
 * Before this, success was a sentence in a visually hidden live region. A sighted user saw
 * the form reset and nothing else, and had to find the new row to learn whether it worked.
 * The live region stays; this is its visible equivalent.
 *
 * **It hands over when reading ends.** The destination unmounts it as soon as the document
 * reaches a state the worker does not leave, and the row takes over, with the outcome and
 * the action. While both were on screen they told the same story twice.
 *
 * **Steps reached, never steps ahead.** A document's route is not fixed: it can stop at
 * Unsupported, at No text found or at Failed, as well as arriving at Needs your
 * confirmation. So this lists only what has happened, and says in a sentence what reading
 * may lead to, which is a statement rather than a stage.
 */
export function UploadProgress({ displayName }: { displayName: string }): JSX.Element {
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
        <li data-step="current">
          <StatusGlyph name="clock" size={14} />
          <span>Reading document…</span>
        </li>
      </ol>

      <p className="cw-upload-progress__note">
        Any values it finds, like travel dates, will be ready to review in the list below.
        You can leave this page while it reads.
      </p>
    </section>
  );
}
