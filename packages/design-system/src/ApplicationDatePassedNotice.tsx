/**
 * The notice for a case whose application date has already gone by.
 *
 * **This is not the stale notice and must not read like one.** Stale means the inputs
 * beneath a conclusion moved and it has not been rechecked, so a recalculation settles it.
 * This means the five-year window every residence figure is measured over has *closed* —
 * and no recalculation fixes that, because nothing is wrong with the arithmetic. "451 days
 * across 16 April 2022 to 15 April 2027" stays true of that window forever. What has
 * changed is whether it is still the window the applicant means.
 *
 * So the wording never says the figures are wrong, out of date, or unreliable. It says the
 * date has passed and what that makes the figures describe, and it offers the one action
 * that helps: choose a date that has not.
 *
 * `KNOWN_LIMITATIONS.md` entry 11 is what this closes. A case left alone until its date
 * went by read as supported against a window that had already ended, which is the
 * false-reassurance shape CLAUDE.md §2.7 ranks as the most important thing to get right.
 *
 * Three signals so it survives greyscale: a left rule, a glyph, and the words.
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";

export interface ApplicationDatePassedNoticeProps {
  /** The date the case is measured against, already formatted for display. */
  applicationDate: string;
  /** Where to go to choose another one. Omitted where the screen is already that place. */
  href?: string | null;
}

export function ApplicationDatePassedNotice({
  applicationDate,
  href,
}: ApplicationDatePassedNoticeProps): JSX.Element {
  return (
    <p className="cw-date-passed-notice" role="note">
      <StatusGlyph name="history" size={16} />
      <span>
        Your proposed application date, <strong>{applicationDate}</strong>, has passed.
        Everything below is measured over the five years ending on it, so it describes a
        period that is now behind you rather than the application you are preparing.{" "}
        {href ? <a href={href}>Choose a new date</a> : "Choose a new date"} to assess this
        case against a window you can still apply in.
      </span>
    </p>
  );
}
